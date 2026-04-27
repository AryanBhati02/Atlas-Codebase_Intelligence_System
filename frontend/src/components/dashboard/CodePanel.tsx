




import React, { useState, useRef, useEffect } from "react";
import Editor from "@monaco-editor/react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileCode2,
  Hash,
  Activity,
  HardDrive,
  Brain,
  Sparkles,
  Loader2,
  Code2,
  GraduationCap,
  MessageCircleQuestion,
  Box,
  GitFork,
  MessageSquare,
} from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { useThemeStore } from "../../store/themeStore";
import { analyzeCode } from "../../api/api";
import { AIPanel } from "./AIPanel";
import { CollaborationPanel } from "../collaboration/CollaborationPanel";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function mapLanguage(lang: string | null | undefined): string {
  if (!lang) return "plaintext";
  const map: Record<string, string> = {
    Python: "python",
    JavaScript: "javascript",
    TypeScript: "typescript",
    Java: "java",
    Go: "go",
    Rust: "rust",
    "C++": "cpp",
    C: "c",
    HTML: "html",
    CSS: "css",
    JSON: "json",
    Markdown: "markdown",
    YAML: "yaml",
    Shell: "shell",
    Ruby: "ruby",
    PHP: "php",
  };
  return map[lang] || "plaintext";
}

type Tab = "code" | "ai" | "collab";

export function CodePanel() {
  const {
    selectedFile,
    fileContent,
    sessionId,
    parsedFiles,
    isAILoading,
    setAIAnalysis,
    setAILoading,
  } = useAppStore();

  const theme = useThemeStore((s) => s.theme);
  const [activeTab, setActiveTab] = useState<Tab>("code");
  const editorRef = useRef<any>(null);


  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (editorRef.current && detail?.line) {
        editorRef.current.revealLineInCenter(detail.line);
        editorRef.current.setPosition({ lineNumber: detail.line, column: 1 });
      }
    };
    window.addEventListener("scroll-to-line", handler);
    return () => window.removeEventListener("scroll-to-line", handler);
  }, []);


  useEffect(() => {
    const switchToAI = () => setActiveTab("ai");
    window.addEventListener("cmd:show-ai-tab", switchToAI);
    window.addEventListener("cmd:show-advanced-ai", switchToAI);
    return () => {
      window.removeEventListener("cmd:show-ai-tab", switchToAI);
      window.removeEventListener("cmd:show-advanced-ai", switchToAI);
    };
  }, []);

  const parsedData = parsedFiles.find((f) => f.path === selectedFile);

  const handleEditorMount = (editor: any) => {
    editorRef.current = editor;
  };

  const handleAnalyzeSelection = async () => {
    if (!editorRef.current || !sessionId || !selectedFile) return;
    const selection = editorRef.current.getSelection();
    const selectedCode = editorRef.current.getModel()?.getValueInRange(selection);
    if (!selectedCode?.trim()) return;

    setAILoading(true);
    setActiveTab("ai");
    try {
      const result = await analyzeCode(
        sessionId, selectedFile, selectedCode,
        selection.startLineNumber, selection.endLineNumber
      );
      setAIAnalysis(result.analysis, result.source);
    } catch {
      setAIAnalysis("Failed to analyze selection.", "error");
    } finally {
      setAILoading(false);
    }
  };


  if (!selectedFile) {
    return (
      <>
        <div className="panel-header">
          <h2>Code & AI</h2>
        </div>
        <div className="flex-1 flex flex-col items-center justify-center text-center px-6">
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.4, ease: [0.25, 0.46, 0.45, 0.94] }}
          >
            <div
              className="w-12 h-12 rounded-2xl flex items-center justify-center mb-4 mx-auto"
              style={{
                background: "var(--gradient-brand-icon)",
                border: "1px solid var(--gradient-brand-icon-border)",
              }}
            >
              <Code2 className="w-5 h-5 text-accent-gold/50" />
            </div>
            <p className="text-[11px] font-medium mb-1" style={{ color: "var(--text-secondary)" }}>
              Select a file to view
            </p>
            <p className="text-[10px] mb-5" style={{ color: "var(--text-muted)" }}>
              Click a file in the explorer or a node in the graph
            </p>

            <div className="flex flex-col gap-1.5 w-full max-w-[180px] mx-auto">
              <motion.button
                onClick={() => setActiveTab("ai")}
                whileHover={{ scale: 1.02, y: -1 }}
                whileTap={{ scale: 0.98 }}
                className="flex items-center gap-2 px-3 py-2 rounded-lg text-[10px] font-medium
                  bg-purple-500/[0.05] text-purple-300/70 border border-purple-500/10
                  hover:bg-purple-500/10 hover:text-purple-300 transition-all duration-300"
              >
                <GraduationCap className="w-3 h-3" />
                Open Beginner Guide
              </motion.button>
              <motion.button
                onClick={() => setActiveTab("ai")}
                whileHover={{ scale: 1.02, y: -1 }}
                whileTap={{ scale: 0.98 }}
                className="flex items-center gap-2 px-3 py-2 rounded-lg text-[10px] font-medium
                  bg-accent-cyan/[0.05] text-accent-cyan/70 border border-accent-cyan/10
                  hover:bg-accent-cyan/10 hover:text-accent-cyan transition-all duration-300"
              >
                <MessageCircleQuestion className="w-3 h-3" />
                Ask a Question
              </motion.button>
            </div>
          </motion.div>
        </div>
      </>
    );
  }

  return (
    <>
      { }
      <div className="panel-header flex-col items-start gap-1.5">
        <div className="flex items-center gap-2 w-full">
          <FileCode2 className="w-3 h-3 text-accent-gold/60 shrink-0" />
          <span className="text-[10.5px] font-medium truncate flex-1 font-mono" style={{ color: "var(--text-primary)" }}>
            {selectedFile}
          </span>
        </div>

        { }
        {parsedData && (
          <div className="flex items-center gap-2 w-full">
            <MemoStatChip icon={Hash} value={`${parsedData.loc}`} label="LOC" />
            <MemoStatChip icon={HardDrive} value={formatBytes(parsedData.size_bytes)} />
            <MemoStatChip icon={Activity} value={`${(parsedData.complexity_score * 100).toFixed(0)}%`} />
            {parsedData.functions.length > 0 && (
              <MemoStatChip icon={GitFork} value={`${parsedData.functions.length}`} label="fn" />
            )}
            {parsedData.classes.length > 0 && (
              <MemoStatChip icon={Box} value={`${parsedData.classes.length}`} label="cls" />
            )}
          </div>
        )}
      </div>

      { }
      <div className="flex shrink-0" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
        <MemoTabButton
          active={activeTab === "code"}
          onClick={() => setActiveTab("code")}
          icon={Code2}
          label="Code"
        />
        <MemoTabButton
          active={activeTab === "ai"}
          onClick={() => setActiveTab("ai")}
          icon={Brain}
          label="AI Intelligence"
          badge={isAILoading}
        />
        <MemoTabButton
          active={activeTab === "collab"}
          onClick={() => setActiveTab("collab")}
          icon={MessageSquare}
          label="Comments"
        />
      </div>

      { }
      <AnimatePresence mode="wait">
        {activeTab === "code" ? (
          <motion.div
            key="code"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="flex-1 flex flex-col min-h-0"
          >
            <div className="monaco-wrapper" data-theme={theme} style={{ background: theme === "light" ? "#ffffff" : "var(--code-viewer-bg)" }}>
              {fileContent ? (
                <Editor
                  height="100%"
                  language={mapLanguage(fileContent.language)}
                  value={fileContent.content}
                  theme={theme === "light" ? "light" : "vs-dark"}
                  onMount={handleEditorMount}
                  options={{
                    readOnly: true,
                    minimap: { enabled: false },
                    fontSize: 12,
                    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                    lineHeight: 19,
                    padding: { top: 10 },
                    scrollBeyondLastLine: false,
                    renderLineHighlight: "gutter",
                    lineNumbers: "on",
                    glyphMargin: false,
                    folding: true,
                    wordWrap: "on",
                    smoothScrolling: true,
                    cursorBlinking: "smooth",
                    cursorSmoothCaretAnimation: "on",
                  }}
                />
              ) : (
                <div className="flex-1 flex items-center justify-center">
                  <Loader2 className="w-4 h-4 animate-spin" style={{ color: "var(--text-muted)" }} />
                </div>
              )}
            </div>

            { }
            {fileContent && (
              <div className="px-3 py-2 flex items-center gap-2 shrink-0" style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <motion.button
                  onClick={handleAnalyzeSelection}
                  disabled={isAILoading}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-medium
                    bg-accent-cyan/[0.06] text-accent-cyan/80 border border-accent-cyan/10
                    hover:bg-accent-cyan/12 disabled:opacity-30
                    transition-all duration-300"
                >
                  <Sparkles className="w-3 h-3" />
                  Analyze Selection
                </motion.button>
                <motion.button
                  onClick={() => setActiveTab("ai")}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-medium
                    bg-accent-gold/[0.06] text-accent-gold/80 border border-accent-gold/10
                    hover:bg-accent-gold/12 transition-all duration-300"
                >
                  <Brain className="w-3 h-3" />
                  AI Insights
                </motion.button>
              </div>
            )}
          </motion.div>
        ) : activeTab === "ai" ? (
          <motion.div
            key="ai"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="flex-1 flex flex-col min-h-0"
          >
            <AIPanel />
          </motion.div>
        ) : activeTab === "collab" ? (
          <motion.div
            key="collab"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="flex-1 flex flex-col min-h-0"
          >
            <CollaborationPanel />
          </motion.div>
        ) : null}
      </AnimatePresence>
    </>
  );
}



function StatChip({
  icon: Icon,
  value,
  label,
}: {
  icon: typeof Hash;
  value: string;
  label?: string;
}) {
  return (
    <div className="flex items-center gap-1 text-[9px]" style={{ color: "var(--text-tertiary)" }}>
      <Icon className="w-2.5 h-2.5" />
      <span className="tabular-nums">{value}</span>
      {label && <span style={{ color: "var(--text-muted)" }}>{label}</span>}
    </div>
  );
}

const MemoStatChip = React.memo(StatChip);

function TabButton({
  active,
  onClick,
  icon: Icon,
  label,
  badge,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof Code2;
  label: string;
  badge?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`relative flex items-center gap-1.5 px-4 py-2 text-[10px] font-medium transition-all duration-300`}
      style={{
        color: active ? "var(--text-primary)" : "var(--text-muted)",
      }}
    >
      <Icon className="w-3 h-3" />
      {label}
      {badge && <Loader2 className="w-2.5 h-2.5 animate-spin text-accent-cyan" />}
      {active && (
        <motion.div
          layoutId="code-tab-indicator"
          className="absolute bottom-0 left-2 right-2 h-[1px]"
          style={{
            background: "linear-gradient(90deg, transparent, rgba(124, 110, 224, 0.5), transparent)",
          }}
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
        />
      )}
    </button>
  );
}

const MemoTabButton = React.memo(TabButton);
