import * as dagre from "dagre";

interface RawNode {
  id: string;
  type?: string;
  data: Record<string, unknown>;
}

interface RawEdge {
  id: string;
  source: string;
  target: string;
}

type LayoutType = "force" | "hierarchical" | "radial" | "layered";

interface WorkerInput {
  nodes: RawNode[];
  edges: RawEdge[];
  layoutType: LayoutType;
}

interface PositionedNode extends RawNode {
  position: { x: number; y: number };
}

interface WorkerOutput {
  nodes: PositionedNode[];
  edges: RawEdge[];
  error: string | null;
}

self.onmessage = (event: MessageEvent<WorkerInput>): void => {
  try {
    const { nodes, edges, layoutType } = event.data;

    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));

    switch (layoutType) {
      case "hierarchical":
        g.setGraph({ rankdir: "TB", nodesep: 60, ranksep: 80, marginx: 40, marginy: 40 });
        break;
      case "force":
        g.setGraph({ rankdir: "TB", nodesep: 120, ranksep: 120, marginx: 60, marginy: 60 });
        break;
      case "radial":
        g.setGraph({ rankdir: "TB", nodesep: 60, ranksep: 80, marginx: 40, marginy: 40 });
        break;
      case "layered":
        g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 100, marginx: 40, marginy: 40 });
        break;
      default:
        g.setGraph({ rankdir: "TB", nodesep: 60, ranksep: 80, marginx: 40, marginy: 40 });
    }

    for (const node of nodes) {
      const isCluster = node.type === "clusterNode";
      g.setNode(node.id, {
        width: isCluster ? 280 : 200,
        height: isCluster ? 80 : 60,
      });
    }

    for (const edge of edges) {
      if (g.hasNode(edge.source) && g.hasNode(edge.target)) {
        g.setEdge(edge.source, edge.target);
      }
    }

    dagre.layout(g);

    const positioned: PositionedNode[] = nodes.map((node) => {
      const isCluster = node.type === "clusterNode";
      const pos = g.node(node.id);
      return {
        ...node,
        position: {
          x: pos ? pos.x - (isCluster ? 140 : 100) : 0,
          y: pos ? pos.y - (isCluster ? 40 : 30) : 0,
        },
      };
    });

    if (layoutType === "radial") {
      const cx = positioned.reduce((sum, n) => sum + n.position.x, 0) / positioned.length;
      const cy = positioned.reduce((sum, n) => sum + n.position.y, 0) / positioned.length;
      positioned.forEach((n) => {
        const dx = n.position.x - cx;
        const dy = n.position.y - cy;
        const r = Math.sqrt(dx * dx + dy * dy) * 0.8;
        const angle = Math.atan2(dy, dx);
        n.position.x = cx + r * Math.cos(angle);
        n.position.y = cy + r * Math.sin(angle);
      });
    }

    if (layoutType === "force") {
      positioned.forEach((n) => {
        n.position.x += (Math.random() - 0.5) * 40;
        n.position.y += (Math.random() - 0.5) * 40;
      });
    }

    const output: WorkerOutput = { nodes: positioned, edges, error: null };
    self.postMessage(output);
  } catch (err) {
    const output: WorkerOutput = { nodes: [], edges: [], error: String(err) };
    self.postMessage(output);
  }
};
