import { useEffect, useRef, useState, useCallback } from "react";
import type { Node, Edge } from "reactflow";

export interface LayoutResult {
  nodes: Node[];
  edges: Edge[];
}

interface PendingLayout {
  resolve: (result: LayoutResult) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

interface WorkerResponse {
  nodes: Node[];
  edges: Edge[];
  error: string | null;
}

export function useGraphLayout() {
  const [isComputing, setIsComputing] = useState(false);
  const workerRef = useRef<Worker | null>(null);
  const pendingRef = useRef<PendingLayout | null>(null);

  useEffect(() => {
    const worker = new Worker(
      new URL("../workers/graphLayout.worker.ts", import.meta.url),
      { type: "module" }
    );

    worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
      const pending = pendingRef.current;
      if (!pending) return;
      clearTimeout(pending.timer);
      pendingRef.current = null;
      setIsComputing(false);
      const { nodes, edges, error } = event.data;
      if (error) {
        pending.reject(new Error(error));
      } else {
        pending.resolve({ nodes, edges });
      }
    };

    worker.onerror = (event: ErrorEvent) => {
      const pending = pendingRef.current;
      if (!pending) return;
      clearTimeout(pending.timer);
      pendingRef.current = null;
      setIsComputing(false);
      pending.reject(new Error(event.message || "Layout worker error"));
    };

    workerRef.current = worker;

    return () => {
      const pending = pendingRef.current;
      if (pending) {
        clearTimeout(pending.timer);
        pending.reject(new Error("Component unmounted"));
        pendingRef.current = null;
      }
      worker.terminate();
      workerRef.current = null;
    };
  }, []);

  const computeLayout = useCallback(
    (
      nodes: Node[],
      edges: Edge[],
      layoutType: "force" | "hierarchical" | "radial" | "layered" = "hierarchical"
    ): Promise<LayoutResult> => {
      return new Promise<LayoutResult>((resolve, reject) => {
        const worker = workerRef.current;
        if (!worker) {
          reject(new Error("Layout worker not initialized"));
          return;
        }

        const existing = pendingRef.current;
        if (existing) {
          clearTimeout(existing.timer);
          existing.reject(new Error("Superseded by new layout request"));
          pendingRef.current = null;
        }

        setIsComputing(true);

        const timer = setTimeout(() => {
          pendingRef.current = null;
          setIsComputing(false);
          reject(new Error("Layout computation timed out after 30 seconds"));
        }, 30_000);

        pendingRef.current = { resolve, reject, timer };

        const serNodes = nodes.map(({ id, type, data }) => ({ id, type, data }));
        const serEdges = edges.map(({ id, source, target }) => ({ id, source, target }));

        worker.postMessage({ nodes: serNodes, edges: serEdges, layoutType });
      });
    },
    []
  );

  return { computeLayout, isComputing };
}
