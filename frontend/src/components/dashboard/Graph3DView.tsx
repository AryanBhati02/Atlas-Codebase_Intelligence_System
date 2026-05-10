import { useMemo, useCallback, useRef, useState, useEffect } from "react";
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { PerfBridge } from "../PerfOverlayBridge";
import * as THREE from "three";
import { useAppStore } from "../../store/appStore";
import { useThemeStore, type ThemeColors } from "../../store/themeStore";
import { getFileContent, explainFile } from "../../api/api";

const LANG_COLORS: Record<string, string> = {
  Python: "#3b82f6", JavaScript: "#f59e0b", TypeScript: "#38bdf8",
  Java: "#f97316", Go: "#06b6d4", Rust: "#ef4444",
  "C++": "#ec4899", C: "#94a3b8", HTML: "#f43f5e",
  CSS: "#8b5cf6", JSON: "#10b981", Markdown: "#6b7280",
  YAML: "#84cc16", Shell: "#22c55e",
};

function getColor(lang: string | null): string {
  return (lang && LANG_COLORS[lang]) || "#7c6ee0";
}

interface Node3D {
  id: string; label: string; language: string | null;
  complexity: number; position: [number, number, number];
}
interface Edge3D { source: string; target: string; }

function compute3DLayout(
  nodes: { id: string; label: string; language: string | null; complexity_score: number }[],
  edges: { source: string; target: string }[]
): { nodes3d: Node3D[]; edges3d: Edge3D[] } {
  const count = nodes.length;
  if (count === 0) return { nodes3d: [], edges3d: [] };

  const inDeg = new Map<string, number>();
  nodes.forEach((n) => inDeg.set(n.id, 0));
  edges.forEach((e) => inDeg.set(e.target, (inDeg.get(e.target) || 0) + 1));
  const sorted = [...nodes].sort((a, b) => (inDeg.get(a.id) || 0) - (inDeg.get(b.id) || 0));

  const perLayer = Math.max(Math.ceil(count / 5), 1);
  const nodes3d: Node3D[] = sorted.map((n, i) => {
    const layer = Math.floor(i / perLayer);
    const idx = i % perLayer;
    const phi = Math.acos(1 - 2 * (idx + 0.5) / perLayer);
    const theta = Math.PI * (1 + Math.sqrt(5)) * idx;
    const r = 12 + layer * 10;
    return {
      id: n.id, label: n.label, language: n.language,
      complexity: (typeof n.complexity_score === "number" && isFinite(n.complexity_score)) ? n.complexity_score : 0.5,
      position: [r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta)] as [number, number, number],
    };
  });

  const ids = new Set(nodes.map((n) => n.id));
  const edges3d = edges.filter((e) => ids.has(e.source) && ids.has(e.target)).map((e) => ({ source: e.source, target: e.target }));
  return { nodes3d, edges3d };
}

const sharedZoomRef = { current: 0 };
const NODE_CAP = 500;
const CLUSTER_THRESHOLD = 200;
const shownNodesRef = { current: 0 };
const totalNodesRef = { current: 0 };

function getDirName3D(filePath: string): string {
  const slash = filePath.indexOf("/");
  return slash === -1 ? "(root)" : filePath.slice(0, slash);
}

interface RawNode {
  id: string; label: string; language: string | null; complexity_score: number;
}

function buildClusterNodes(rawNodes: RawNode[]): RawNode[] {
  const groups = new Map<string, RawNode[]>();
  rawNodes.forEach((n) => {
    const dir = getDirName3D(n.id);
    if (!groups.has(dir)) groups.set(dir, []);
    groups.get(dir)!.push(n);
  });
  const clusterNodes: RawNode[] = [];
  groups.forEach((members, dir) => {
    const fileCount = members.length;
    const langCounts = new Map<string, number>();
    let totalComplexity = 0;
    members.forEach((m) => {
      totalComplexity += (typeof m.complexity_score === "number" && isFinite(m.complexity_score)) ? m.complexity_score : 0.5;
      if (m.language) langCounts.set(m.language, (langCounts.get(m.language) || 0) + 1);
    });
    let dominantLang: string | null = null;
    let maxCount = 0;
    langCounts.forEach((c, l) => { if (c > maxCount) { maxCount = c; dominantLang = l; } });
    const clusterSize = 0.8 + Math.log10(Math.max(fileCount, 1)) * 0.6;
    clusterNodes.push({
      id: `3d-cluster-${dir}`,
      label: `${dir} (${fileCount} files)`,
      language: dominantLang,
      complexity_score: clusterSize,
    });
  });
  return clusterNodes;
}

function DualModeCamera({ centerOfMass }: { centerOfMass: THREE.Vector3 }) {
  const { camera, gl } = useThree();
  const keys = useRef<Set<string>>(new Set());
  const euler = useRef(new THREE.Euler(0, 0, 0, "YXZ"));
  const isPointerDown = useRef(false);
  const zoomLevel = useRef(0);
  const targetZoom = useRef(0);
  const orbitalAngle = useRef({ theta: 0, phi: Math.PI / 4 });
  const moveSpeed = 15;
  const lookSensitivity = 0.003;
  const orbitalRadius = 50;

  useEffect(() => {
    camera.position.set(0, 5, 20);
    euler.current.setFromQuaternion(camera.quaternion);
  }, [camera]);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (["w", "a", "s", "d", "q", "e", "shift", " "].includes(e.key.toLowerCase())) {
        keys.current.add(e.key.toLowerCase());
        e.preventDefault();
      }
    };
    const up = (e: KeyboardEvent) => keys.current.delete(e.key.toLowerCase());
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); };
  }, []);

  useEffect(() => {
    const dom = gl.domElement;
    const onDown = (e: MouseEvent) => {
      if (e.button === 0 || e.button === 2) isPointerDown.current = true;
    };
    const onUp = () => { isPointerDown.current = false; };
    const onMove = (e: MouseEvent) => {
      if (!isPointerDown.current) return;
      const z = zoomLevel.current;
      if (z < 0.4) {
        euler.current.y -= e.movementX * lookSensitivity;
        euler.current.x -= e.movementY * lookSensitivity;
        euler.current.x = Math.max(-Math.PI / 2 + 0.01, Math.min(Math.PI / 2 - 0.01, euler.current.x));
      } else {
        orbitalAngle.current.theta -= e.movementX * 0.005;
        orbitalAngle.current.phi -= e.movementY * 0.005;
        orbitalAngle.current.phi = Math.max(0.1, Math.min(Math.PI - 0.1, orbitalAngle.current.phi));
      }
    };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      targetZoom.current = Math.max(0, Math.min(1, targetZoom.current + e.deltaY * 0.001));
    };
    const onCtx = (e: MouseEvent) => e.preventDefault();

    dom.addEventListener("mousedown", onDown);
    dom.addEventListener("mouseup", onUp);
    dom.addEventListener("mouseleave", onUp);
    dom.addEventListener("mousemove", onMove);
    dom.addEventListener("wheel", onWheel, { passive: false });
    dom.addEventListener("contextmenu", onCtx);
    return () => {
      dom.removeEventListener("mousedown", onDown);
      dom.removeEventListener("mouseup", onUp);
      dom.removeEventListener("mouseleave", onUp);
      dom.removeEventListener("mousemove", onMove);
      dom.removeEventListener("wheel", onWheel);
      dom.removeEventListener("contextmenu", onCtx);
    };
  }, [gl]);

  useFrame((_, delta) => {
    const dt = Math.min(delta, 0.1);

    zoomLevel.current = THREE.MathUtils.lerp(zoomLevel.current, targetZoom.current, 1 - Math.pow(0.01, dt));
    sharedZoomRef.current = zoomLevel.current;
    const z = zoomLevel.current;

    if (z < 0.4) {
      const dir = new THREE.Vector3();
      const right = new THREE.Vector3();
      camera.getWorldDirection(dir);
      right.crossVectors(dir, camera.up).normalize();

      const speed = moveSpeed * dt * (keys.current.has("shift") ? 2.5 : 1);
      if (keys.current.has("w")) camera.position.addScaledVector(dir, speed);
      if (keys.current.has("s")) camera.position.addScaledVector(dir, -speed);
      if (keys.current.has("a")) camera.position.addScaledVector(right, -speed);
      if (keys.current.has("d")) camera.position.addScaledVector(right, speed);
      if (keys.current.has(" ")) camera.position.y += speed;
      if (keys.current.has("q")) camera.position.y -= speed;

      camera.quaternion.setFromEuler(euler.current);
    } else {
      const { theta, phi } = orbitalAngle.current;
      const r = THREE.MathUtils.lerp(20, orbitalRadius, Math.min((z - 0.4) / 0.6, 1));
      const targetPos = new THREE.Vector3(
        centerOfMass.x + r * Math.sin(phi) * Math.cos(theta),
        centerOfMass.y + r * Math.cos(phi),
        centerOfMass.z + r * Math.sin(phi) * Math.sin(theta)
      );
      camera.position.lerp(targetPos, 1 - Math.pow(0.005, dt));
      camera.lookAt(centerOfMass);
      euler.current.setFromQuaternion(camera.quaternion);
    }
  });

  return null;
}

function InstancedNodes({
  nodes, selectedId, hoveredId, connectedIds, deadFiles, onSelect, onHover, themeColors,
}: {
  nodes: Node3D[];
  selectedId: string | null;
  hoveredId: string | null;
  connectedIds: Set<string> | null;
  deadFiles: Set<string>;
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
  themeColors: ThemeColors;
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null!);
  const dummy = useRef(new THREE.Object3D());
  const prevSelectedId = useRef<string | null>(null);
  const prevHoveredId = useRef<string | null>(null);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nearbyLabelIds = useRef<string[]>([]);
  const nearbyLabelTick = useRef(0);

  const baseSizes = useMemo(() => {
    return nodes.map((n) => {
      const c = (typeof n.complexity === "number" && isFinite(n.complexity)) ? n.complexity : 0.5;
      return 0.35 + c * 0.45;
    });
  }, [nodes]);

  useEffect(() => {
    const im = meshRef.current;
    if (!im) return;
    nodes.forEach((n, i) => {
      const bs = baseSizes[i];
      if (bs === undefined) return;
      dummy.current.position.set(...n.position);
      dummy.current.scale.setScalar(bs);
      dummy.current.updateMatrix();
      im.setMatrixAt(i, dummy.current.matrix);
      const col = new THREE.Color(getColor(n.language));
      im.setColorAt(i, col);
    });
    im.instanceMatrix.needsUpdate = true;
    if (im.instanceColor) im.instanceColor.needsUpdate = true;
  }, [nodes, baseSizes]);

  useFrame(({ camera }, delta) => {
    const im = meshRef.current;
    if (!im) return;

    const dt = Math.min(delta, 0.1);
    const changed =
      selectedId !== prevSelectedId.current ||
      hoveredId !== prevHoveredId.current;

    if (!changed) return;

    const prevSel = prevSelectedId.current;
    const prevHov = prevHoveredId.current;
    prevSelectedId.current = selectedId;
    prevHoveredId.current = hoveredId;

    const indicesToUpdate = new Set<number>();
    const findIdx = (id: string | null) => {
      if (id === null) return -1;
      return nodes.findIndex((n) => n.id === id);
    };

    [prevSel, prevHov, selectedId, hoveredId].forEach((id) => {
      const idx = findIdx(id);
      if (idx >= 0) indicesToUpdate.add(idx);
    });

    indicesToUpdate.forEach((i) => {
      const n = nodes[i];
      const bs = baseSizes[i];
      if (!n || bs === undefined) return;
      const isSel = n.id === selectedId;
      const isHov = n.id === hoveredId;
      const isDim =
        (connectedIds !== null && !connectedIds.has(n.id)) ||
        deadFiles.has(n.id);

      const scaleMultiplier = isSel ? 1.6 : isHov ? 1.25 : 1;
      const targetScale = bs * scaleMultiplier;

      im.getMatrixAt(i, dummy.current.matrix);
      dummy.current.matrix.decompose(
        dummy.current.position,
        dummy.current.quaternion,
        dummy.current.scale
      );
      const curScale = dummy.current.scale.x;
      const newScale = THREE.MathUtils.lerp(curScale, targetScale, 1 - Math.pow(0.001, dt));
      dummy.current.scale.setScalar(isFinite(newScale) ? newScale : targetScale);
      dummy.current.updateMatrix();
      im.setMatrixAt(i, dummy.current.matrix);

      const baseColor = new THREE.Color(getColor(n.language));
      if (isDim) {
        baseColor.lerp(new THREE.Color(0x000000), 0.82);
      } else if (isSel) {
        baseColor.lerp(new THREE.Color(0xffffff), 0.3);
      } else if (isHov) {
        baseColor.lerp(new THREE.Color(0xffffff), 0.15);
      }
      im.setColorAt(i, baseColor);
    });

    im.instanceMatrix.needsUpdate = true;
    if (im.instanceColor) im.instanceColor.needsUpdate = true;

    nearbyLabelTick.current += delta;
    if (nearbyLabelTick.current > 1.0) {
      nearbyLabelTick.current = 0;
      const camPos = camera.position;
      const distances = nodes.map((n, i) => ({
        id: n.id,
        dist: camPos.distanceToSquared(new THREE.Vector3(...n.position)),
        i,
      }));
      distances.sort((a, b) => a.dist - b.dist);
      nearbyLabelIds.current = distances.slice(0, 5).map((d) => d.id);
    }
  });

  const handleClick = useCallback(
    (e: ThreeEvent<MouseEvent>) => {
      e.stopPropagation();
      const id = e.instanceId !== undefined ? nodes[e.instanceId]?.id : null;
      if (id) onSelect(id);
    },
    [nodes, onSelect]
  );

  const handlePointerMove = useCallback(
    (e: ThreeEvent<PointerEvent>) => {
      e.stopPropagation();
      if (hoverTimer.current) return;
      hoverTimer.current = setTimeout(() => {
        hoverTimer.current = null;
        const id = e.instanceId !== undefined ? nodes[e.instanceId]?.id ?? null : null;
        onHover(id);
      }, 50);
    },
    [nodes, onHover]
  );

  const handlePointerOut = useCallback(() => {
    if (hoverTimer.current) { clearTimeout(hoverTimer.current); hoverTimer.current = null; }
    onHover(null);
  }, [onHover]);

  const labelNodes = useMemo(() => {
    const ids = new Set<string>(nearbyLabelIds.current);
    if (selectedId) ids.add(selectedId);
    if (hoveredId) ids.add(hoveredId);
    return nodes.filter((n) => ids.has(n.id));
  }, [nodes, selectedId, hoveredId]);

  if (nodes.length === 0) return null;

  return (
    <>
      <instancedMesh
        ref={meshRef}
        args={[undefined, undefined, nodes.length]}
        onClick={handleClick}
        onPointerMove={handlePointerMove}
        onPointerOut={handlePointerOut}
      >
        <sphereGeometry args={[1, 16, 16]} />
        <meshStandardMaterial
          roughness={0.3}
          metalness={0.4}
          emissive="#7c6ee0"
          emissiveIntensity={0.05}
        />
      </instancedMesh>

      {labelNodes.map((n) => {
        const isSel = n.id === selectedId;
        const isHov = n.id === hoveredId;
        const c = (typeof n.complexity === "number" && isFinite(n.complexity)) ? n.complexity : 0.5;
        const bs = 0.35 + c * 0.45;
        const scaleMultiplier = isSel ? 1.6 : isHov ? 1.25 : 1;
        const isDim =
          (connectedIds !== null && !connectedIds.has(n.id)) ||
          deadFiles.has(n.id);
        return (
          <Html
            key={n.id}
            position={[
              n.position[0],
              n.position[1] + bs * scaleMultiplier + 0.7,
              n.position[2],
            ]}
            center
            distanceFactor={10}
            style={{
              pointerEvents: "none",
              userSelect: "none",
              whiteSpace: "nowrap",
              fontSize: isSel ? "14px" : "10px",
              fontWeight: isSel ? 700 : 500,
              fontFamily: "Inter, system-ui, sans-serif",
              color: isSel
                ? themeColors.labelSelectedColor
                : isDim
                ? themeColors.labelDimmed
                : themeColors.labelColor,
              textShadow: "0 2px 8px rgba(0,0,0,0.9), 0 0 4px rgba(0,0,0,0.95)",
              opacity: isDim ? 0.35 : 1,
              padding: isSel ? "2px 8px" : "1px 4px",
              borderRadius: "6px",
              background: isSel ? themeColors.labelSelectedBg : "transparent",
              border: isSel
                ? `1px solid ${themeColors.labelSelectedColor}25`
                : "none",
              backdropFilter: isSel ? "blur(4px)" : "none",
            }}
          >
            {n.label}
          </Html>
        );
      })}
    </>
  );
}

function InstancedClusterNodes({
  nodes, hoveredId, onSelect, onHover,
}: {
  nodes: Node3D[];
  hoveredId: string | null;
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null!);
  const dummy = useRef(new THREE.Object3D());
  const prevHoveredId = useRef<string | null>(null);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const im = meshRef.current;
    if (!im) return;
    nodes.forEach((n, i) => {
      dummy.current.position.set(...n.position);
      dummy.current.scale.setScalar(n.complexity);
      dummy.current.updateMatrix();
      im.setMatrixAt(i, dummy.current.matrix);
      im.setColorAt(i, new THREE.Color(getColor(n.language)));
    });
    im.instanceMatrix.needsUpdate = true;
    if (im.instanceColor) im.instanceColor.needsUpdate = true;
  }, [nodes]);

  useFrame((_, delta) => {
    const im = meshRef.current;
    if (!im) return;
    if (hoveredId === prevHoveredId.current) return;
    const prevHov = prevHoveredId.current;
    prevHoveredId.current = hoveredId;
    const dt = Math.min(delta, 0.1);
    const toUpdate = new Set<number>();
    [prevHov, hoveredId].forEach((id) => {
      if (id === null) return;
      const idx = nodes.findIndex((n) => n.id === id);
      if (idx >= 0) toUpdate.add(idx);
    });
    toUpdate.forEach((i) => {
      const n = nodes[i];
      if (!n) return;
      const isHov = n.id === hoveredId;
      const baseScale = n.complexity;
      const targetScale = isHov ? baseScale * 1.2 : baseScale;
      im.getMatrixAt(i, dummy.current.matrix);
      dummy.current.matrix.decompose(dummy.current.position, dummy.current.quaternion, dummy.current.scale);
      const cur = dummy.current.scale.x;
      const next = THREE.MathUtils.lerp(cur, targetScale, 1 - Math.pow(0.001, dt));
      dummy.current.scale.setScalar(isFinite(next) ? next : targetScale);
      dummy.current.updateMatrix();
      im.setMatrixAt(i, dummy.current.matrix);
      const col = new THREE.Color(getColor(n.language));
      if (isHov) col.lerp(new THREE.Color(0xffffff), 0.25);
      im.setColorAt(i, col);
    });
    im.instanceMatrix.needsUpdate = true;
    if (im.instanceColor) im.instanceColor.needsUpdate = true;
  });

  const handleClick = useCallback((e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    const id = e.instanceId !== undefined ? nodes[e.instanceId]?.id : null;
    if (id) onSelect(id);
  }, [nodes, onSelect]);

  const handlePointerMove = useCallback((e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    if (hoverTimer.current) return;
    hoverTimer.current = setTimeout(() => {
      hoverTimer.current = null;
      const id = e.instanceId !== undefined ? nodes[e.instanceId]?.id ?? null : null;
      onHover(id);
    }, 50);
  }, [nodes, onHover]);

  const handlePointerOut = useCallback(() => {
    if (hoverTimer.current) { clearTimeout(hoverTimer.current); hoverTimer.current = null; }
    onHover(null);
  }, [onHover]);

  if (nodes.length === 0) return null;

  return (
    <>
      <instancedMesh
        ref={meshRef}
        args={[undefined, undefined, nodes.length]}
        onClick={handleClick}
        onPointerMove={handlePointerMove}
        onPointerOut={handlePointerOut}
      >
        <icosahedronGeometry args={[1, 2]} />
        <meshStandardMaterial
          roughness={0.2}
          metalness={0.5}
          emissive="#a78bfa"
          emissiveIntensity={0.12}
        />
      </instancedMesh>

      {nodes.map((n) => {
        const isHov = n.id === hoveredId;
        return (
          <Html
            key={n.id}
            position={[n.position[0], n.position[1] + n.complexity + 0.9, n.position[2]]}
            center
            distanceFactor={12}
            style={{
              pointerEvents: "none", userSelect: "none", whiteSpace: "nowrap",
              fontSize: isHov ? "13px" : "11px",
              fontWeight: isHov ? 700 : 600,
              fontFamily: "Inter, system-ui, sans-serif",
              color: isHov ? "#e0d7ff" : "#c4b5fd",
              textShadow: "0 2px 10px rgba(0,0,0,0.95), 0 0 6px rgba(0,0,0,0.9)",
              padding: "2px 8px", borderRadius: "6px",
              background: isHov ? "rgba(124,110,224,0.25)" : "transparent",
              border: isHov ? "1px solid rgba(167,139,250,0.4)" : "none",
              backdropFilter: isHov ? "blur(4px)" : "none",
            }}
          >
            {n.label}
          </Html>
        );
      })}
    </>
  );
}

function EdgeLines({ edges, nodeMap, selectedId, hoveredId, themeColors }: {
  edges: Edge3D[]; nodeMap: Map<string, Node3D>; selectedId: string | null; hoveredId: string | null;
  themeColors: ThemeColors;
}) {
  const { positions, colors } = useMemo(() => {
    const pos: number[] = [], col: number[] = [];
    const activeId = selectedId || hoveredId;
    edges.forEach((e) => {
      const src = nodeMap.get(e.source), tgt = nodeMap.get(e.target);
      if (!src || !tgt) return;
      pos.push(...src.position, ...tgt.position);
      const conn = activeId && (e.source === activeId || e.target === activeId);
      if (conn) col.push(...themeColors.edgeActive, ...themeColors.edgeActive);
      else if (activeId) col.push(...themeColors.edgeDimmed, ...themeColors.edgeDimmed);
      else col.push(...themeColors.edgeDefault, ...themeColors.edgeDefault);
    });
    return { positions: new Float32Array(pos), colors: new Float32Array(col) };
  }, [edges, nodeMap, selectedId, hoveredId, themeColors]);

  if (positions.length === 0) return null;
  return (
    <lineSegments>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} />
      </bufferGeometry>
      <lineBasicMaterial vertexColors transparent opacity={0.3} linewidth={1} depthWrite={false} />
    </lineSegments>
  );
}

function GridFloor({ themeColors }: { themeColors: ThemeColors }) {
  const groupRef = useRef<THREE.Group>(null!);
  const gridPrimary = themeColors.threeGridPrimary;
  const gridSecondary = themeColors.threeGridSecondary;
  const floorColor = themeColors.threeFloorPlane;

  useFrame(() => {
    if (!groupRef.current) return;

    const z = sharedZoomRef.current;
    const targetOpacity = z > 0.35 ? Math.min((z - 0.35) / 0.3, 0.6) : 0;
    const gridMat = (groupRef.current.children[0] as any)?.material;
    const planeMat = (groupRef.current.children[1] as any)?.material;
    if (gridMat) { gridMat.opacity = targetOpacity; gridMat.transparent = true; }
    if (planeMat) { planeMat.opacity = targetOpacity * 0.5; }
    groupRef.current.visible = z > 0.1;
  });

  return (
    <group ref={groupRef} position={[0, -15, 0]}>
      <gridHelper args={[120, 60, gridPrimary, gridSecondary]} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]}>
        <planeGeometry args={[120, 120]} />
        <meshBasicMaterial color={floorColor} transparent opacity={0} depthWrite={false} />
      </mesh>
    </group>
  );
}

function ThemeUpdater({ themeColors }: { themeColors: ThemeColors }) {
  const { scene } = useThree();

  useEffect(() => {
    scene.background = new THREE.Color(themeColors.threeBg);
    if (scene.fog instanceof THREE.Fog) {
      scene.fog.color.set(themeColors.threeFog);
    }
  }, [themeColors, scene]);

  return null;
}

function Graph3DScene({ expandedCluster3D, onExpandCluster }: {
  expandedCluster3D: string | null;
  onExpandCluster: (clusterId: string) => void;
}) {
  const { graphData, selectedFile, sessionId, setSelectedFile, setFileContent,
    setAIExplanation, setAILoading, showDeadCode, deadCodeData } = useAppStore();
  const themeColors = useThemeStore((s) => s.colors);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const isClustered = (graphData?.nodes.length ?? 0) > CLUSTER_THRESHOLD && expandedCluster3D === null;

  const clusterChildMap = useMemo(() => {
    if (!graphData) return new Map<string, RawNode[]>();
    const m = new Map<string, RawNode[]>();
    graphData.nodes.forEach((n) => {
      const key = `3d-cluster-${getDirName3D(n.id)}`;
      if (!m.has(key)) m.set(key, []);
      m.get(key)!.push(n);
    });
    return m;
  }, [graphData]);

  const { nodes3d, edges3d, nodeMap, connectedIds, centerOfMass, totalNodes } = useMemo(() => {
    const empty = { nodes3d: [] as Node3D[], edges3d: [] as Edge3D[], nodeMap: new Map<string, Node3D>(), connectedIds: null as Set<string> | null, centerOfMass: new THREE.Vector3(), totalNodes: 0 };
    if (!graphData) return empty;

    let rawNodes: RawNode[];
    let rawEdges: { source: string; target: string }[];

    if (isClustered) {
      rawNodes = buildClusterNodes(graphData.nodes);
      rawEdges = [];
    } else if (expandedCluster3D !== null) {
      const children = clusterChildMap.get(expandedCluster3D) ?? [];
      rawNodes = children;
      const childIds = new Set(children.map((c) => c.id));
      rawEdges = graphData.edges.filter((e) => childIds.has(e.source) && childIds.has(e.target));
    } else {
      rawNodes = graphData.nodes;
      rawEdges = graphData.edges;
    }

    const { nodes3d: allNodes3d, edges3d } = compute3DLayout(rawNodes, rawEdges);
    const totalNodes = allNodes3d.length;
    const nodes3d = totalNodes > NODE_CAP
      ? [...allNodes3d].sort((a, b) => b.complexity - a.complexity).slice(0, NODE_CAP)
      : allNodes3d;

    const nodeMap = new Map<string, Node3D>();
    const com = new THREE.Vector3();
    nodes3d.forEach((n) => { nodeMap.set(n.id, n); com.add(new THREE.Vector3(...n.position)); });
    if (nodes3d.length > 0) com.divideScalar(nodes3d.length);

    let connectedIds: Set<string> | null = null;
    const activeId = selectedFile || hoveredId;
    if (activeId && !isClustered) {
      connectedIds = new Set<string>([activeId]);
      edges3d.forEach((e) => {
        if (e.source === activeId) connectedIds!.add(e.target);
        if (e.target === activeId) connectedIds!.add(e.source);
      });
    }
    return { nodes3d, edges3d, nodeMap, connectedIds, centerOfMass: com, totalNodes };
  }, [graphData, selectedFile, hoveredId, isClustered, expandedCluster3D, clusterChildMap]);

  const deadFiles = useMemo(() => {
    if (!showDeadCode || !deadCodeData) return new Set<string>();
    return new Set(deadCodeData.dead_files.map((d) => d.path));
  }, [showDeadCode, deadCodeData]);

  const handleSelect = useCallback(async (id: string) => {
    if (isClustered) {
      onExpandCluster(id);
      return;
    }
    if (!sessionId) return;
    setSelectedFile(id);
    try { const c = await getFileContent(sessionId, id); setFileContent(c); } catch { }
    try { setAILoading(true); const ai = await explainFile(sessionId, id); setAIExplanation(ai.explanation, ai.source); } catch { }
    finally { setAILoading(false); }
  }, [isClustered, onExpandCluster, sessionId, setSelectedFile, setFileContent, setAIExplanation, setAILoading]);

  const handleBgClick = useCallback(() => {
    if (!isClustered) setSelectedFile(null);
  }, [isClustered, setSelectedFile]);

  useEffect(() => {
    shownNodesRef.current = nodes3d.length;
    totalNodesRef.current = totalNodes;
  });

  if (!graphData || graphData.nodes.length === 0) return null;

  return (
    <>
      <DualModeCamera centerOfMass={centerOfMass} />
      <ThemeUpdater themeColors={themeColors} />

      <ambientLight intensity={themeColors.ambientIntensity} />
      <pointLight position={[30, 30, 30]} intensity={0.9} color="#f6c445" distance={100} />
      <pointLight position={[-20, -15, 20]} intensity={0.5} color="#22d3ee" distance={80} />
      <pointLight position={[0, -25, -15]} intensity={0.35} color="#8b5cf6" distance={80} />
      <pointLight position={[0, 20, 0]} intensity={0.2} color="#e2e8f0" distance={60} />

      <GridFloor themeColors={themeColors} />

      <EdgeLines edges={edges3d} nodeMap={nodeMap} selectedId={isClustered ? null : selectedFile} hoveredId={hoveredId} themeColors={themeColors} />

      {totalNodes > NODE_CAP && (
        <Html position={[0, 22, 0]} center style={{
          pointerEvents: "none", userSelect: "none", fontSize: "11px",
          fontFamily: "Inter, system-ui, sans-serif", color: themeColors.labelDimmed,
          background: themeColors.toolbarBg, border: `1px solid ${themeColors.toolbarBorder}`,
          padding: "4px 10px", borderRadius: "8px", backdropFilter: "blur(6px)", whiteSpace: "nowrap",
        }}>
          Showing {NODE_CAP} of {totalNodes} nodes · sorted by complexity
        </Html>
      )}

      {isClustered ? (
        <InstancedClusterNodes
          nodes={nodes3d}
          hoveredId={hoveredId}
          onSelect={handleSelect}
          onHover={setHoveredId}
        />
      ) : (
        <InstancedNodes
          nodes={nodes3d}
          selectedId={selectedFile}
          hoveredId={hoveredId}
          connectedIds={connectedIds}
          deadFiles={deadFiles}
          onSelect={handleSelect}
          onHover={setHoveredId}
          themeColors={themeColors}
        />
      )}

      <mesh position={[0, 0, -50]} onClick={handleBgClick} visible={false}>
        <planeGeometry args={[300, 300]} />
        <meshBasicMaterial transparent opacity={0} />
      </mesh>
    </>
  );
}

export function Graph3DView() {
  const { graphData, setSelectedFile } = useAppStore();
  const themeColors = useThemeStore((s) => s.colors);
  const [showControls, setShowControls] = useState(true);
  const [expandedCluster3D, setExpandedCluster3D] = useState<string | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setShowControls(false), 6000);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    setExpandedCluster3D(null);
  }, [graphData]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelectedFile(null);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [setSelectedFile]);

  const isClustered = (graphData?.nodes.length ?? 0) > CLUSTER_THRESHOLD && expandedCluster3D === null;

  if (!graphData || graphData.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>No graph data for 3D view</p>
      </div>
    );
  }

  return (
    <div className="w-full h-full relative" style={{ background: themeColors.threeBg, minHeight: 0, position: "relative", zIndex: 2 }}>
      <Canvas
        dpr={[1, 1.5]}
        gl={{ antialias: true, alpha: false, powerPreference: "high-performance", failIfMajorPerformanceCaveat: false }}
        camera={{ fov: 65, near: 0.1, far: 3000 }}
        style={{ position: "absolute", inset: 0, cursor: "crosshair" }}
        onCreated={({ gl }) => {
          gl.domElement.addEventListener("webglcontextlost", (e) => { e.preventDefault(); });
        }}
      >
        <color attach="background" args={[themeColors.threeBg]} />
        <fog attach="fog" args={[themeColors.threeFog, 500, 2500]} />
        <Graph3DScene
          expandedCluster3D={expandedCluster3D}
          onExpandCluster={setExpandedCluster3D}
        />
        <PerfBridge />
      </Canvas>

      {expandedCluster3D !== null && (
        <button
          onClick={() => setExpandedCluster3D(null)}
          style={{
            position: "absolute", top: "1rem", right: "1rem", zIndex: 20,
            display: "flex", alignItems: "center", gap: "6px",
            padding: "6px 14px", borderRadius: "10px", cursor: "pointer",
            fontSize: "11px", fontWeight: 600, fontFamily: "Inter, system-ui, sans-serif",
            color: themeColors.labelSelectedColor,
            background: themeColors.toolbarBg,
            border: `1px solid ${themeColors.labelSelectedColor}55`,
            backdropFilter: "blur(8px)",
            transition: "opacity 0.2s",
          }}
        >
          ← Back to clusters
        </button>
      )}

      <div
        className="absolute top-16 left-3 z-10 flex flex-col gap-1 px-3 py-2 rounded-xl backdrop-blur-md transition-opacity duration-700"
        style={{
          opacity: showControls ? 1 : 0,
          pointerEvents: showControls ? "auto" : "none",
          background: themeColors.toolbarBg,
          border: `1px solid ${themeColors.toolbarBorder}`,
        }}
        onMouseEnter={() => setShowControls(true)}
      >
        <span className="text-[9px] font-bold uppercase tracking-wider mb-0.5" style={{ color: themeColors.labelSelectedColor }}>Controls</span>
        <span className="text-[9px]" style={{ color: themeColors.toolbarText }}><kbd className="font-semibold" style={{ color: themeColors.labelColor }}>W A S D</kbd> — Move</span>
        <span className="text-[9px]" style={{ color: themeColors.toolbarText }}><kbd className="font-semibold" style={{ color: themeColors.labelColor }}>Space / Q</kbd> — Up / Down</span>
        <span className="text-[9px]" style={{ color: themeColors.toolbarText }}><kbd className="font-semibold" style={{ color: themeColors.labelColor }}>Shift</kbd> — Sprint</span>
        <span className="text-[9px]" style={{ color: themeColors.toolbarText }}><kbd className="font-semibold" style={{ color: themeColors.labelColor }}>Click + Drag</kbd> — Look</span>
        <span className="text-[9px]" style={{ color: themeColors.toolbarText }}><kbd className="font-semibold" style={{ color: themeColors.labelColor }}>Scroll</kbd> — Zoom In / Out</span>
      </div>

      <div className="absolute bottom-3 left-3 z-10 flex items-center gap-2 px-2.5 py-1 rounded-lg backdrop-blur-sm"
        style={{ background: themeColors.toolbarBg, border: `1px solid ${themeColors.toolbarBorder}` }}>
        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        <span className="text-[9px] font-medium" style={{ color: "var(--text-muted)" }}>
          {isClustered
            ? `clusters · ${shownNodesRef.current} dirs · ${graphData.nodes.length} files`
            : expandedCluster3D !== null
              ? `files · ${shownNodesRef.current}${
                  totalNodesRef.current > shownNodesRef.current
                    ? ` of ${totalNodesRef.current}`
                    : ""
                } shown`
              : `3D · ${shownNodesRef.current}${
                  totalNodesRef.current > shownNodesRef.current
                    ? ` of ${totalNodesRef.current}`
                    : ""
                } nodes · ${graphData.edges.length} edges`
          }
        </span>
      </div>

      <div
        className="absolute top-16 left-3 w-32 h-32 z-10"
        onMouseEnter={() => setShowControls(true)}
      />
    </div>
  );
}
