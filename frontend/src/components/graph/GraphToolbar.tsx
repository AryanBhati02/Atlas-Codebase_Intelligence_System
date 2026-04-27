import { useState, useCallback, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Flame,
  Ghost,
  LayoutGrid,
  Maximize2,
  Download,
  Loader2,
  ChevronDown,
  Box,
} from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { useThemeStore } from "../../store/themeStore";
import { getDeadCode } from "../../api/api";

const LAYOUTS = [
  { id: "force", label: "Force-Directed" },
  { id: "hierarchical", label: "Hierarchical" },
  { id: "radial", label: "Radial" },
  { id: "layered", label: "Layered" },
] as const;

export type LayoutMode = (typeof LAYOUTS)[number]["id"];

interface GraphToolbarProps {
  heatmapOn: boolean;
  onToggleHeatmap: () => void;
  layout: LayoutMode;
  onChangeLayout: (l: LayoutMode) => void;
  onFitView: () => void;
}

export function GraphToolbar({
  heatmapOn,
  onToggleHeatmap,
  layout,
  onChangeLayout,
  onFitView,
}: GraphToolbarProps) {
  const {
    sessionId,
    showDeadCode,
    toggleDeadCode,
    deadCodeData,
    setDeadCodeData,
    isDeadCodeLoading,
    setDeadCodeLoading,
    show3DGraph,
    toggle3DGraph,
  } = useAppStore();
  const themeColors = useThemeStore((s) => s.colors);

  const [layoutOpen, setLayoutOpen] = useState(false);

  const handleDeadCodeToggle = useCallback(async () => {
    if (!sessionId) return;
    if (!showDeadCode && !deadCodeData) {
      setDeadCodeLoading(true);
      try {
        const data = await getDeadCode(sessionId);
        setDeadCodeData(data);
      } catch {
        setDeadCodeLoading(false);
      }
    }
    toggleDeadCode();
  }, [sessionId, showDeadCode, deadCodeData, setDeadCodeData, toggleDeadCode, setDeadCodeLoading]);

  useEffect(() => {
    const onInternal = () => { handleDeadCodeToggle(); };
    window.addEventListener("cmd:dead-code-toggle-internal", onInternal);
    return () => window.removeEventListener("cmd:dead-code-toggle-internal", onInternal);
  }, [handleDeadCodeToggle]);

  const handleExport = useCallback(() => {
    const svgEl = document.querySelector(".react-flow svg.react-flow__edges") as SVGElement;
    if (svgEl) {
      const svgData = new XMLSerializer().serializeToString(svgEl);
      const blob = new Blob([svgData], { type: "image/svg+xml;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.download = "graph.svg";
      link.href = url;
      link.click();
      URL.revokeObjectURL(url);
    }
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94], delay: 0.4 }}
      className="absolute top-3 right-3 z-20 flex items-center gap-1 px-1.5 py-1
        rounded-xl backdrop-filter backdrop-blur-xl shadow-2xl"
      style={{
        background: themeColors.toolbarBg,
        border: `1px solid ${themeColors.toolbarBorder}`,
      }}
    >
      <ToolBtn
        active={heatmapOn}
        onClick={onToggleHeatmap}
        tooltip="Heatmap"
        activeColor="#f59e0b"
        themeColors={themeColors}
      >
        <Flame className="w-3.5 h-3.5" />
      </ToolBtn>

      <ToolBtn
        active={showDeadCode}
        onClick={handleDeadCodeToggle}
        tooltip="Dead Code"
        activeColor="#ef4444"
        themeColors={themeColors}
      >
        {isDeadCodeLoading ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <Ghost className="w-3.5 h-3.5" />
        )}
      </ToolBtn>

      <ToolBtn
        active={show3DGraph}
        onClick={toggle3DGraph}
        tooltip={show3DGraph ? "Switch to 2D" : "Switch to 3D"}
        activeColor="#22d3ee"
        themeColors={themeColors}
      >
        <Box className="w-3.5 h-3.5" />
      </ToolBtn>

      <Divider themeColors={themeColors} />

      <div className="relative">
        <ToolBtn
          active={layoutOpen}
          onClick={() => setLayoutOpen(!layoutOpen)}
          tooltip="Layout"
          themeColors={themeColors}
        >
          <LayoutGrid className="w-3.5 h-3.5" />
          <ChevronDown className="w-2.5 h-2.5 ml-0.5 opacity-50" />
        </ToolBtn>

        <AnimatePresence>
          {layoutOpen && (
            <motion.div
              initial={{ opacity: 0, y: -6, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -6, scale: 0.95 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
              className="absolute right-0 top-full mt-1.5 w-36
                rounded-lg backdrop-blur-xl shadow-2xl overflow-hidden z-30"
              style={{
                background: themeColors.toolbarDropdownBg,
                border: `1px solid ${themeColors.toolbarBorder}`,
              }}
            >
              {LAYOUTS.map((l) => (
                <button
                  key={l.id}
                  onClick={() => { onChangeLayout(l.id); setLayoutOpen(false); }}
                  className="w-full text-left px-3 py-1.5 text-[10px] transition-all duration-200"
                  style={{
                    color: layout === l.id ? themeColors.toolbarDropdownActiveText : themeColors.toolbarDropdownText,
                    background: layout === l.id ? themeColors.toolbarDropdownActiveBg : "transparent",
                  }}
                  onMouseEnter={(e) => {
                    if (layout !== l.id) {
                      e.currentTarget.style.color = themeColors.toolbarHover;
                      e.currentTarget.style.background = themeColors.toolbarDropdownHover;
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (layout !== l.id) {
                      e.currentTarget.style.color = themeColors.toolbarDropdownText;
                      e.currentTarget.style.background = "transparent";
                    }
                  }}
                >
                  {l.label}
                </button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <Divider themeColors={themeColors} />

      <ToolBtn onClick={onFitView} tooltip="Fit" themeColors={themeColors}>
        <Maximize2 className="w-3.5 h-3.5" />
      </ToolBtn>

      <ToolBtn onClick={handleExport} tooltip="Export" themeColors={themeColors}>
        <Download className="w-3.5 h-3.5" />
      </ToolBtn>

      <AnimatePresence>
        {showDeadCode && deadCodeData && (
          <motion.div
            initial={{ opacity: 0, scale: 0.8, width: 0 }}
            animate={{ opacity: 1, scale: 1, width: "auto" }}
            exit={{ opacity: 0, scale: 0.8, width: 0 }}
            className="flex items-center gap-1 ml-0.5 px-2 py-0.5
              rounded-md bg-red-500/[0.06] border border-red-500/10 overflow-hidden"
          >
            <Ghost className="w-2.5 h-2.5 text-red-400/70" />
            <span className="text-[9px] text-red-400/70 font-medium whitespace-nowrap">
              {deadCodeData.summary.dead_files_count} dead
            </span>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

import type { ThemeColors } from "../../store/themeStore";

function ToolBtn({
  children,
  active,
  onClick,
  tooltip,
  activeColor,
  themeColors,
}: {
  children: React.ReactNode;
  active?: boolean;
  onClick: () => void;
  tooltip?: string;
  activeColor?: string;
  themeColors: ThemeColors;
}) {
  return (
    <motion.button
      onClick={onClick}
      title={tooltip}
      whileHover={{ scale: 1.08 }}
      whileTap={{ scale: 0.92 }}
      className="flex items-center gap-0.5 p-1.5 rounded-lg text-xs transition-all duration-200"
      style={{
        color: active ? (activeColor || themeColors.toolbarActiveText) : themeColors.toolbarText,
        background: active ? themeColors.toolbarActiveBg : "transparent",
      }}
    >
      {children}
    </motion.button>
  );
}

function Divider({ themeColors }: { themeColors: ThemeColors }) {
  return <div className="w-px h-3.5 mx-0.5" style={{ background: themeColors.toolbarBorder }} />;
}
