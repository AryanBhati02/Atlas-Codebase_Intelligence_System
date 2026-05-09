import { useFrame, useThree } from "@react-three/fiber";
import { usePerfStore } from "../stores/perfStore";

export function PerfBridge(): null {
  const { gl } = useThree();

  useFrame(() => {
    usePerfStore.getState().setDrawCalls(gl.info.render.calls);
  });

  return null;
}
