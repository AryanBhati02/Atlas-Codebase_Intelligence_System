import { useFrame, useThree } from "@react-three/fiber";
import { usePerfStore } from "../stores/perfStore";

// Mounted inside the Canvas tree. Reads gl.info.render.calls every frame
// and writes it to the perf store so PerfOverlay can read it imperatively.
export function PerfBridge(): null {
  const { gl } = useThree();

  useFrame(() => {
    usePerfStore.getState().setDrawCalls(gl.info.render.calls);
  });

  return null;
}
