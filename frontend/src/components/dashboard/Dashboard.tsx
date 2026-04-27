import React, { useEffect, useCallback, useRef, useState, useMemo } from "react";
import { motion } from "framer-motion";
import {
  RotateCcw,
  GitBranch,
  Upload,
  FileCode2,
  Activity,
  Settings,
  Layers,
  Search,
  Sun,
  Moon,
  PanelRightClose,
  PanelRight,
} from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { useThemeStore } from "../../store/themeStore";
import { analyzeWithProgress, getAIStatus, getCommentCounts } from "../../api/api";
import type { AIStatusResponse } from "../../types";
import { FileExplorer } from "./FileExplorer";
import { GraphView } from "./GraphView";
import { CodePanel } from "./CodePanel";
import { SettingsPanel } from "../settings/SettingsPanel";
import { CommandPalette } from "./CommandPalette";
import { EmptyState } from "./EmptyState";
import { SidebarEmptyState } from "./SidebarEmptyState";

export function Dashboard() {
  const {
    sessionId,
    repoName,
    sourceType,
    isAnalyzed,
    isAnalyzing,
    parsedFiles,
    setAnalyzing,
    setAnalysisProgress,
    setAnalysisResult,
    setError,
    reset,
    toggleSettings,
    aiStatus,
    setAIStatus,
    setCommentCounts,
    isChatPanelOpen,
    toggleChatPanel,
    addRecentRepo,
  } = useAppStore();

  const theme = useThemeStore((s) => s.theme);
  const toggleTheme = useThemeStore((s) => s.toggleTheme);

  const glowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let mx = 0, my = 0, cx = 0, cy = 0;
    let raf: number;

    const onMove = (e: MouseEvent) => { mx = e.clientX; my = e.clientY; };

    const tick = () => {
      cx += (mx - cx) * 0.12;
      cy += (my - cy) * 0.12;
      if (glowRef.current) {
        glowRef.current.style.left = `${cx}px`;
        glowRef.current.style.top = `${cy}px`;
      }
      raf = requestAnimationFrame(tick);
    };

    window.addEventListener("mousemove", onMove, { passive: true });
    raf = requestAnimationFrame(tick);
    return () => {
      window.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(raf);
    };
  }, []);

  const pollStatus = useCallback(async () => {
    try {
      const status = await getAIStatus();
      setAIStatus(status);
    } catch { }
  }, [setAIStatus]);

  useEffect(() => {
    pollStatus();
    const interval = setInterval(pollStatus, 30_000);
    return () => clearInterval(interval);
  }, [pollStatus]);

  const [progressStage, setProgressStage] = useState("starting");
  const [progressCurrent, setProgressCurrent] = useState(0);
  const [progressTotal, setProgressTotal] = useState(0);

  useEffect(() => {
    if (!sessionId || isAnalyzed) return;

    setAnalyzing(true);
    setProgressStage("starting");
    setProgressCurrent(0);
    setProgressTotal(0);

    let cancelled = false;

    const { promise, abort } = analyzeWithProgress(
      sessionId,
      (stage, current, total) => {
        if (!cancelled) {
          setProgressStage(stage);
          setProgressCurrent(current);
          setProgressTotal(total);
          setAnalysisProgress({ stage, current, total });
        }
      }
    );

    promise
      .then((data) => {
        if (!cancelled) {
          setAnalysisResult(data.parsed_files, data.graph);
          if (repoName) {
            const repoUrl = sourceType === "github"
              ? `https://github.com/${repoName}`
              : repoName;
            addRecentRepo({
              name: repoName,
              url: repoUrl,
              sourceType: (sourceType as "github" | "zip") || "github",
              lastOpened: Date.now(),
            });
          }
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError("Analysis failed. " + (err?.message || ""));
          setAnalyzing(false);
        }
      });

    return () => {
      cancelled = true;
      abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, isAnalyzed]);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await getCommentCounts(sessionId);
        if (!cancelled) setCommentCounts(data.counts);
      } catch { }
    })();
    return () => { cancelled = true; };
  }, [sessionId, setCommentCounts]);

  const stageLabels: Record<string, string> = {
    starting: "Initializing…",
    parsing: "Parsing files",
    scoring: "Scoring complexity",
    graph: "Building dependency graph",
    saving: "Caching results",
    done: "Complete!",
    error: "Error",
  };

  const stageWeights: Record<string, { base: number; weight: number }> = {
    starting: { base: 0, weight: 5 },
    parsing: { base: 5, weight: 65 },
    scoring: { base: 70, weight: 10 },
    graph: { base: 80, weight: 10 },
    saving: { base: 90, weight: 5 },
    done: { base: 100, weight: 0 },
    error: { base: 0, weight: 0 },
  };

  const getOverallPct = () => {
    const w = stageWeights[progressStage] || { base: 0, weight: 0 };
    if (progressStage === "done") return 100;
    if (progressStage === "error") return 0;
    const intraStage = progressTotal > 0 ? progressCurrent / progressTotal : 0;
    return Math.min(100, Math.round(w.base + w.weight * intraStage));
  };

  const hasSession = !!sessionId && isAnalyzed;

  const complexAvg = useMemo(() =>
    parsedFiles.length > 0
      ? (parsedFiles.reduce((s, f) => s + f.complexity_score, 0) / parsedFiles.length).toFixed(2)
      : "0",
    [parsedFiles]
  );

  const totalLoc = useMemo(() => parsedFiles.reduce((s, f) => s + f.loc, 0), [parsedFiles]);

  if (isAnalyzing) {
    const overallPct = getOverallPct();
    const sourceLabel = sourceType === "zip" ? "ZIP Archive" : "Repository";
    return (
      <div className="analyzing-overlay">
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            textAlign: "center",
            width: "100%",
            maxWidth: "360px",
          }}
        >
          <div className="analyzing-spinner mb-6" />
          <motion.h2
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-lg font-semibold mb-2"
            style={{ color: "var(--text-primary)" }}
          >
            Analyzing {sourceLabel}
          </motion.h2>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1 }}
            className="mb-1"
          >
            <span
              className="text-sm font-semibold tabular-nums"
              style={{
                background: "var(--gradient-brand)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              {overallPct}%
            </span>
          </motion.p>

          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="text-xs mb-4"
            style={{ color: "var(--text-tertiary)" }}
          >
            {stageLabels[progressStage] || progressStage}
            {progressStage === "parsing" && progressTotal > 0 && (
              <span className="ml-1 tabular-nums" style={{ color: "var(--accent-cyan)" }}>
                — {progressCurrent}/{progressTotal} files
              </span>
            )}
          </motion.p>

          <div style={{ width: "100%" }}>
            <div
              className="rounded-full overflow-hidden"
              style={{ height: "5px", background: "var(--border-light)" }}
            >
              <motion.div
                className="rounded-full"
                style={{
                  height: "100%",
                  background: "var(--gradient-brand)",
                  boxShadow: "0 0 12px var(--accent-purple-glow)",
                }}
                initial={{ width: "0%" }}
                animate={{ width: `${overallPct}%` }}
                transition={{ duration: 0.4, ease: "easeOut" }}
              />
            </div>
          </div>

          {(progressStage === "starting" || (progressTotal === 0 && progressStage !== "done")) && (
            <div className="flex gap-1.5 mt-3">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="w-1.5 h-1.5 rounded-full animate-bounce"
                  style={{
                    animationDelay: `${i * 0.15}s`,
                    backgroundColor: "var(--bounce-dot-color)",
                  }}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-layout">
      <div ref={glowRef} className="cursor-glow" />

      <header className="dashboard-header">
        <div className="flex items-center gap-2.5">
          <motion.div
            className="w-7 h-7 rounded-lg flex items-center justify-center overflow-hidden"
            whileHover={{ scale: 1.08, rotate: 3 }}
            transition={{ type: "spring", stiffness: 400, damping: 15 }}
          >
            <img src="/icon.png" alt="Logo" className="w-full h-full object-cover" />
          </motion.div>
          <div>
            <h1 className="text-[11px] font-bold leading-none tracking-tight" style={{ color: "var(--text-primary)" }}>
              Codebase Intelligence
            </h1>
            {hasSession && (
              <div className="flex items-center gap-1.5 mt-0.5">
                {sourceType === "github" ? (
                  <GitBranch className="w-2.5 h-2.5" style={{ color: "var(--text-tertiary)" }} />
                ) : (
                  <Upload className="w-2.5 h-2.5" style={{ color: "var(--text-tertiary)" }} />
                )}
                <span className="text-[10px] font-medium truncate max-w-[200px]" style={{ color: "var(--text-muted)" }}>
                  {repoName}
                </span>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 ml-auto">
          {hasSession && <AIStatusIndicator status={aiStatus} />}

          {hasSession && (
            <>
              <div className="stat-pill flex items-center gap-1.5 px-2.5 py-1 rounded-lg" style={{ background: "var(--bg-input)", border: "1px solid var(--border-light)" }}>
                <FileCode2 className="w-3 h-3" style={{ color: "var(--accent-cyan)", opacity: 0.7 }} />
                <span className="text-[10px] font-medium" style={{ color: "var(--text-tertiary)" }}>
                  {parsedFiles.length}
                </span>
              </div>

              <div className="stat-pill flex items-center gap-1.5 px-2.5 py-1 rounded-lg" style={{ background: "var(--bg-input)", border: "1px solid var(--border-light)" }}>
                <Layers className="w-3 h-3" style={{ color: "var(--accent-purple)", opacity: 0.7 }} />
                <span className="text-[10px] font-medium" style={{ color: "var(--text-tertiary)" }}>
                  {totalLoc.toLocaleString()} LOC
                </span>
              </div>

              <div className="stat-pill flex items-center gap-1.5 px-2.5 py-1 rounded-lg" style={{ background: "var(--bg-input)", border: "1px solid var(--border-light)" }}>
                <Activity className="w-3 h-3" style={{ color: "var(--accent-gold)", opacity: 0.7 }} />
                <span className="text-[10px] font-medium" style={{ color: "var(--text-tertiary)" }}>
                  {complexAvg}
                </span>
              </div>
            </>
          )}

          <motion.button
            onClick={() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true }))}
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.95 }}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-medium transition-colors duration-200"
            style={{
              color: "var(--text-tertiary)",
              background: "var(--bg-input)",
              border: "1px solid var(--border-light)",
            }}
            title="Command Palette (Ctrl+K)"
          >
            <Search className="w-3 h-3" />
            <span className="hidden sm:inline">Search</span>
            <kbd className="ml-0.5 px-1 py-0.5 rounded text-[8px] font-semibold"
              style={{
                background: "var(--bg-input)",
                border: "1px solid var(--border-medium)",
                color: "var(--text-tertiary)",
              }}>
              ⌘K
            </kbd>
          </motion.button>

          <motion.button
            onClick={toggleTheme}
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.95 }}
            className="flex items-center p-1.5 rounded-lg transition-colors duration-200"
            style={{
              color: "var(--text-tertiary)",
              background: "var(--bg-input)",
              border: "1px solid var(--border-light)",
            }}
            title={theme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"}
            aria-label="Toggle theme"
            tabIndex={0}
          >
            {theme === "dark" ? (
              <Sun className="w-3.5 h-3.5" />
            ) : (
              <Moon className="w-3.5 h-3.5" />
            )}
          </motion.button>

          <motion.button
            onClick={toggleChatPanel}
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.95 }}
            className="flex items-center p-1.5 rounded-lg transition-colors duration-200"
            style={{
              color: "var(--text-tertiary)",
              background: "var(--bg-input)",
              border: "1px solid var(--border-light)",
            }}
            title={isChatPanelOpen ? "Hide Chat Panel" : "Show Chat Panel"}
            aria-label="Toggle chat panel"
            tabIndex={0}
          >
            {isChatPanelOpen ? (
              <PanelRightClose className="w-3.5 h-3.5" />
            ) : (
              <PanelRight className="w-3.5 h-3.5" />
            )}
          </motion.button>

          <motion.button
            onClick={toggleSettings}
            whileHover={{ scale: 1.06 }}
            whileTap={{ scale: 0.95 }}
            className="flex items-center p-1.5 rounded-lg transition-colors duration-200"
            style={{
              color: "var(--text-tertiary)",
              background: "var(--bg-input)",
              border: "1px solid var(--border-light)",
            }}
            title="Settings"
          >
            <Settings className="w-3.5 h-3.5" />
          </motion.button>

          {hasSession && (
            <motion.button
              onClick={reset}
              whileHover={{ scale: 1.06 }}
              whileTap={{ scale: 0.95 }}
              className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-[10px] font-medium transition-colors duration-200"
              style={{
                color: "var(--text-tertiary)",
                background: "var(--bg-input)",
                border: "1px solid var(--border-light)",
              }}
            >
              <RotateCcw className="w-3 h-3" />
              New
            </motion.button>
          )}
        </div>
      </header>

      <ResizablePanels hasSession={hasSession} isChatPanelOpen={isChatPanelOpen} />

      <SettingsPanel />
      <CommandPalette />
    </div>
  );
}

function ResizablePanels({
  hasSession,
  isChatPanelOpen,
}: {
  hasSession: boolean;
  isChatPanelOpen: boolean;
}) {
  const [leftWidth, setLeftWidth] = useState(260);
  const [rightWidth, setRightWidth] = useState(380);
  const dragRef = useRef<{
    side: "left" | "right";
    startX: number;
    startWidth: number;
  } | null>(null);

  const LEFT_MIN = 180;
  const LEFT_MAX = 400;
  const RIGHT_MIN = 200;
  const RIGHT_MAX = 600;

  const handleMouseDown = useCallback(
    (side: "left" | "right") => (e: React.MouseEvent) => {
      e.preventDefault();
      dragRef.current = {
        side,
        startX: e.clientX,
        startWidth: side === "left" ? leftWidth : rightWidth,
      };
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [leftWidth, rightWidth]
  );

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!dragRef.current) return;
      const { side, startX, startWidth } = dragRef.current;
      const delta = e.clientX - startX;
      if (side === "left") {
        setLeftWidth(Math.min(LEFT_MAX, Math.max(LEFT_MIN, startWidth + delta)));
      } else {
        setRightWidth(Math.min(RIGHT_MAX, Math.max(RIGHT_MIN, startWidth - delta)));
      }
    };

    const onMouseUp = () => {
      if (dragRef.current) {
        dragRef.current = null;
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
    return () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };
  }, []);

  return (
    <div className="dashboard-panels">
      <motion.div
        className="panel panel-left"
        initial={{ x: -20, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
        style={{ width: leftWidth, minWidth: LEFT_MIN, maxWidth: LEFT_MAX }}
      >
        {hasSession ? <FileExplorer /> : <SidebarEmptyState />}
      </motion.div>

      <div
        className="resize-handle"
        onMouseDown={handleMouseDown("left")}
      />

      <motion.div
        className="panel panel-center"
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94], delay: 0.1 }}
      >
        {hasSession ? <GraphView /> : <EmptyState />}
      </motion.div>

      <div
        className="resize-handle"
        onMouseDown={handleMouseDown("right")}
      />

      <motion.div
        className={`panel panel-right${isChatPanelOpen ? "" : " collapsed"}`}
        initial={{ x: 20, opacity: 0 }}
        animate={{ x: 0, opacity: isChatPanelOpen ? 1 : 0 }}
        transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
        style={isChatPanelOpen ? { width: rightWidth, minWidth: RIGHT_MIN, maxWidth: RIGHT_MAX } : undefined}
      >
        {hasSession && <CodePanel />}
      </motion.div>
    </div>
  );
}


const AIStatusIndicator = React.memo(function AIStatusIndicator({ status }: { status: AIStatusResponse | null }) {
  if (!status) {
    return (
      <div className="stat-pill flex items-center gap-1.5 px-2.5 py-1 rounded-lg" style={{ background: "var(--bg-input)", border: "1px solid var(--border-light)" }}>
        <div className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--text-faint)" }} />
        <span className="text-[10px] font-medium" style={{ color: "var(--text-tertiary)" }}>AI</span>
      </div>
    );
  }

  const anyAPI = status.groq || status.gemini || status.mistral || status.huggingface;
  const isLocal = status.ollama;

  if (isLocal && anyAPI) {
    return (
      <div className="stat-pill flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/[0.04] border border-emerald-500/10">
        <div className="relative">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
          <div className="absolute inset-0 w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping opacity-30" />
        </div>
        <span className="text-[10px] text-emerald-400/80 font-medium">AI Ready</span>
      </div>
    );
  }

  if (isLocal || anyAPI) {
    return (
      <div className="stat-pill flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/[0.04] border border-amber-500/10">
        <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />
        <span className="text-[10px] text-amber-400/80 font-medium">
          {isLocal ? "Local" : "API"}
        </span>
      </div>
    );
  }

  return (
    <div className="stat-pill flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-red-500/[0.04] border border-red-500/10">
      <div className="w-1.5 h-1.5 rounded-full bg-red-400/60" />
      <span className="text-[10px] text-red-400/60 font-medium">Offline</span>
    </div>
  );
}
);
