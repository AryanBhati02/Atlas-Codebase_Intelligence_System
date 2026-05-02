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
    const r = 8 + layer * 6;
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

function NodeSphere({ node, isSelected, isHovered, isDimmed, onSelect, onHover, themeColors }: {
  node: Node3D; isSelected: boolean; isHovered: boolean; isDimmed: boolean;
  onSelect: (id: string) => void; onHover: (id: string | null) => void;
  themeColors: ThemeColors;
}) {
  const meshRef = useRef<THREE.Mesh>(null!);
  const glowRef = useRef<THREE.Mesh>(null!);
  const ringRef = useRef<THREE.Mesh>(null!);
  const color = getColor(node.language);
  const scale = isSelected ? 1.6 : isHovered ? 1.25 : 1;
  const c = (typeof node.complexity === "number" && isFinite(node.complexity)) ? node.complexity : 0.5;
  const baseSize = 0.35 + c * 0.45;

  useFrame((_, delta) => {
    const dt = Math.min(delta, 0.1);
    if (meshRef.current) {
      const t = scale * baseSize;
      if (isFinite(t)) {
        const s = meshRef.current.scale.x;
        const l = THREE.MathUtils.lerp(s, t, 1 - Math.pow(0.001, dt));
        if (isFinite(l)) meshRef.current.scale.setScalar(l);
      }
    }
    if (glowRef.current) {
      const gt = (isSelected ? 3.5 : isHovered ? 2.5 : 1.8) * baseSize;
      if (isFinite(gt)) {
        const g = glowRef.current.scale.x;
        const gl2 = THREE.MathUtils.lerp(g, gt, 1 - Math.pow(0.001, dt));
        if (isFinite(gl2)) glowRef.current.scale.setScalar(gl2);
      }
      const mat = glowRef.current.material as THREE.MeshBasicMaterial;
      const to = isSelected ? 0.15 : isHovered ? 0.08 : 0.025;
      const no = THREE.MathUtils.lerp(mat.opacity, to, 1 - Math.pow(0.01, dt));
      if (isFinite(no)) mat.opacity = no;
    }

    if (ringRef.current) {
      ringRef.current.rotation.z += delta * 0.5;
      ringRef.current.rotation.x += delta * 0.3;
      const targetScale = isSelected ? baseSize * 2.2 : 0;
      const rs = ringRef.current.scale.x;
      ringRef.current.scale.setScalar(THREE.MathUtils.lerp(rs, targetScale, 1 - Math.pow(0.001, dt)));
    }
  });

  const handleClick = useCallback((e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation(); onSelect(node.id);
  }, [node.id, onSelect]);

  return (
    <group position={node.position}>
      <mesh ref={glowRef}>
        <sphereGeometry args={[1, 16, 16]} />
        <meshBasicMaterial color={color} transparent opacity={0.025} depthWrite={false} />
      </mesh>

      <mesh ref={ringRef}>
        <torusGeometry args={[1, 0.02, 8, 48]} />
        <meshBasicMaterial color={themeColors.labelSelectedColor} transparent opacity={0.6} depthWrite={false} />
      </mesh>

      <mesh ref={meshRef} onClick={handleClick}
        onPointerEnter={(e) => { e.stopPropagation(); onHover(node.id); }}
        onPointerLeave={() => onHover(null)}
      >
        <sphereGeometry args={[1, 24, 24]} />
        <meshStandardMaterial
          color={color} emissive={color}
          emissiveIntensity={isSelected ? 0.7 : isHovered ? 0.35 : 0.1}
          roughness={0.25} metalness={0.3}
          transparent opacity={isDimmed ? 0.12 : 1}
        />
      </mesh>

      {(isSelected || isHovered || !isDimmed) && (
        <Html position={[0, baseSize * scale + 0.7, 0]} center distanceFactor={10}
          style={{
            pointerEvents: "none", userSelect: "none", whiteSpace: "nowrap",
            fontSize: isSelected ? "14px" : "10px",
            fontWeight: isSelected ? 700 : 500,
            fontFamily: "Inter, system-ui, sans-serif",
            color: isSelected ? themeColors.labelSelectedColor : isDimmed ? themeColors.labelDimmed : themeColors.labelColor,
            textShadow: "0 2px 8px rgba(0,0,0,0.9), 0 0 4px rgba(0,0,0,0.95)",
            opacity: isDimmed ? 0.35 : 1,
            padding: isSelected ? "2px 8px" : "1px 4px",
            borderRadius: "6px",
            background: isSelected ? themeColors.labelSelectedBg : "transparent",
            border: isSelected ? `1px solid ${themeColors.labelSelectedColor}25` : "none",
            backdropFilter: isSelected ? "blur(4px)" : "none",
          }}
        >
          {node.label}
        </Html>
      )}
    </group>
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

function Graph3DScene() {
  const { graphData, selectedFile, sessionId, setSelectedFile, setFileContent,
    setAIExplanation, setAILoading, showDeadCode, deadCodeData } = useAppStore();
  const themeColors = useThemeStore((s) => s.colors);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const { nodes3d, edges3d, nodeMap, connectedIds, centerOfMass } = useMemo(() => {
    if (!graphData) return { nodes3d: [], edges3d: [], nodeMap: new Map<string, Node3D>(), connectedIds: null, centerOfMass: new THREE.Vector3() };
    const { nodes3d, edges3d } = compute3DLayout(graphData.nodes, graphData.edges);
    const nodeMap = new Map<string, Node3D>();
    const com = new THREE.Vector3();
    nodes3d.forEach((n) => { nodeMap.set(n.id, n); com.add(new THREE.Vector3(...n.position)); });
    if (nodes3d.length > 0) com.divideScalar(nodes3d.length);

    let connectedIds: Set<string> | null = null;
    const activeId = selectedFile || hoveredId;
    if (activeId) {
      connectedIds = new Set<string>([activeId]);
      edges3d.forEach((e) => {
        if (e.source === activeId) connectedIds!.add(e.target);
        if (e.target === activeId) connectedIds!.add(e.source);
      });
    }
    return { nodes3d, edges3d, nodeMap, connectedIds, centerOfMass: com };
  }, [graphData, selectedFile, hoveredId]);

  const deadFiles = useMemo(() => {
    if (!showDeadCode || !deadCodeData) return new Set<string>();
    return new Set(deadCodeData.dead_files.map((d) => d.path));
  }, [showDeadCode, deadCodeData]);

  const handleSelect = useCallback(async (id: string) => {
    if (!sessionId) return;
    setSelectedFile(id);
    try { const c = await getFileContent(sessionId, id); setFileContent(c); } catch { }
    try { setAILoading(true); const ai = await explainFile(sessionId, id); setAIExplanation(ai.explanation, ai.source); } catch { }
    finally { setAILoading(false); }
  }, [sessionId, setSelectedFile, setFileContent, setAIExplanation, setAILoading]);

  const handleBgClick = useCallback(() => setSelectedFile(null), [setSelectedFile]);

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

      <EdgeLines edges={edges3d} nodeMap={nodeMap} selectedId={selectedFile} hoveredId={hoveredId} themeColors={themeColors} />

      {nodes3d.map((node) => (
        <NodeSphere key={node.id} node={node}
          isSelected={selectedFile === node.id} isHovered={hoveredId === node.id}
          isDimmed={(connectedIds !== null && !connectedIds.has(node.id)) || deadFiles.has(node.id)}
          onSelect={handleSelect} onHover={setHoveredId}
          themeColors={themeColors}
        />
      ))}

      <mesh position={[0, 0, -50]} onClick={handleBgClick} visible={false}>
        <planeGeometry args={[300, 300]} />
        <meshBasicMaterial transparent opacity={0} />
      </mesh>
    </>
  );
}

export function Graph3DView() {
  const { graphData } = useAppStore();
  const themeColors = useThemeStore((s) => s.colors);
  const [showControls, setShowControls] = useState(true);

  useEffect(() => {
    const t = setTimeout(() => setShowControls(false), 6000);
    return () => clearTimeout(t);
  }, []);

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
        <Graph3DScene />
        <PerfBridge />
      </Canvas>

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
          3D · {graphData.nodes.length} nodes · {graphData.edges.length} edges
        </span>
      </div>

      <div
        className="absolute top-16 left-3 w-32 h-32 z-10"
        onMouseEnter={() => setShowControls(true)}
      />
    </div>
  );
}
