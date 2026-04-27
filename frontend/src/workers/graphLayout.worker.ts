/// <reference lib="webworker" />
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

interface WorkerInput {
  nodes: RawNode[];
  edges: RawEdge[];
  direction: "TB" | "LR";
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
    const { nodes, edges, direction } = event.data;

    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));
    g.setGraph({
      rankdir: direction,
      ranksep: 80,
      nodesep: 60,
      marginx: 40,
      marginy: 40,
    });

    for (const node of nodes) {
      g.setNode(node.id, { width: 200, height: 60 });
    }

    for (const edge of edges) {
      if (g.hasNode(edge.source) && g.hasNode(edge.target)) {
        g.setEdge(edge.source, edge.target);
      }
    }

    dagre.layout(g);

    const positioned: PositionedNode[] = nodes.map((node) => {
      const pos = g.node(node.id);
      return {
        ...node,
        position: {
          x: pos ? pos.x - 100 : 0,
          y: pos ? pos.y - 30 : 0,
        },
      };
    });

    const output: WorkerOutput = { nodes: positioned, edges, error: null };
    self.postMessage(output);
  } catch (err) {
    const output: WorkerOutput = { nodes: [], edges: [], error: String(err) };
    self.postMessage(output);
  }
};
