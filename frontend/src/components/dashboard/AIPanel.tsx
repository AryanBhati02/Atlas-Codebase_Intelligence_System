import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Brain,
  Sparkles,
  Cpu,
  GraduationCap,
  MessageCircleQuestion,
  Send,
  FileCode2,
  ChevronRight,
  BookOpen,
  Clock,
  Rocket,
  X,
  Square,
} from "lucide-react";
import { useSessionStore } from "../../store/sessionStore";
import { useAiStore } from "../../store/aiStore";
import { getFileContent } from "../../api/api";
import { streamAI } from "../../api/aiStream";
import type { StreamControl } from "../../api/aiStream";
import { AdvancedAIPanel } from "./AdvancedAIPanel";

type AITab = "explain" | "analyze" | "beginner" | "qa" | "advanced";

function SourceBadge({
  source,
  isStreaming,
}: {
  source: string | null;
  isStreaming?: boolean;
}) {
  if (isStreaming) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/15 animate-pulse">
        <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan animate-ping inline-block" />
        Streaming…
      </span>
    );
  }
  if (!source) return null;
  if (source === "ollama") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/15">
        <Cpu className="w-3 h-3" />
        Ollama AI
      </span>
    );
  }
  if (source === "error") return null;
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-accent-gold/10 text-accent-gold border border-accent-gold/15">
      <Sparkles className="w-3 h-3" />
      AI Analysis
    </span>
  );
}

function StreamCursor() {
  return (
    <motion.span
      className="inline-block w-[2px] h-[1em] bg-accent-cyan/80 ml-0.5 align-middle"
      animate={{ opacity: [1, 1, 0, 0] }}
      transition={{ duration: 0.8, repeat: Infinity, times: [0, 0.5, 0.5, 1] }}
    />
  );
}

function CancelButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="ml-auto flex items-center gap-1 px-2 py-0.5 rounded text-[10px]
        text-slate-400 hover:text-red-400 border border-white/5 hover:border-red-400/20
        transition-colors"
      title="Cancel streaming"
    >
      <Square className="w-2.5 h-2.5" /> Cancel
    </button>
  );
}

function EmptyPrompt({
  icon: Icon,
  primary,
  secondary,
  color = "accent-cyan",
}: {
  icon: typeof Brain;
  primary: string;
  secondary: string;
  color?: string;
}) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center px-6 py-12">
      <div
        className={`w-12 h-12 rounded-2xl flex items-center justify-center mb-3 bg-${color}/10 border border-${color}/12`}
      >
        <Icon className={`w-5 h-5 text-${color}`} />
      </div>
      <p className="text-xs text-slate-400 mb-1">{primary}</p>
      <p className="text-[10px] text-slate-600">{secondary}</p>
    </div>
  );
}

function ExplainTab() {
  const selectedFile = useSessionStore((s) => s.selectedFile);
  const sessionId = useSessionStore((s) => s.sessionId);

  const [content, setContent] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const streamedFileRef = useRef<string | null>(null);
  const ctrlRef = useRef<StreamControl | null>(null);

  useEffect(() => {
    if (!selectedFile || !sessionId) {
      setContent("");
      setIsStreaming(false);
      setErrorMsg(null);
      return;
    }
    if (streamedFileRef.current === selectedFile) return;
    streamedFileRef.current = selectedFile;

    ctrlRef.current?.cancel();
    setContent("");
    setErrorMsg(null);
    setIsStreaming(true);

    const ctrl = streamAI(
      "/ai/explain/stream",
      { session_id: sessionId, file_path: selectedFile },
      {
        onChunk: (text) => setContent((c) => c + text),
        onDone: () => {
          setIsStreaming(false);
          ctrlRef.current = null;
        },
        onError: (err) => {
          setIsStreaming(false);
          ctrlRef.current = null;
          let msg = err.message;
          try {
            const body = JSON.parse(msg.replace(/^HTTP \d+: /, ""));
            if (body?.detail?.error) msg = body.detail.error;
            else if (body?.detail) msg = String(body.detail);
          } catch {
            // use raw message
          }
          setErrorMsg(msg);
        },
      }
    );
    ctrlRef.current = ctrl;

    return () => {
      ctrl.cancel();
    };
  }, [selectedFile, sessionId]);

  const handleCancel = () => {
    ctrlRef.current?.cancel();
    setIsStreaming(false);
  };

  if (!selectedFile) {
    return (
      <EmptyPrompt
        icon={Brain}
        primary="No file selected"
        secondary="Click a file to get an AI-powered explanation"
      />
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-4 pt-3 pb-1 flex items-center gap-2 shrink-0">
        <SourceBadge source={content ? "ai" : null} isStreaming={isStreaming} />
        <span className="text-[10px] text-slate-600 truncate font-mono">
          {selectedFile}
        </span>
        {isStreaming && <CancelButton onClick={handleCancel} />}
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3 ai-content">
        {errorMsg ? (
          <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-400">
            <X className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        ) : content ? (
          <>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
            {isStreaming && <StreamCursor />}
          </>
        ) : isStreaming ? (
          <div className="flex items-center gap-2 text-[11px] text-slate-500 mt-2">
            <StreamCursor />
            <span>Analysing…</span>
          </div>
        ) : (
          <p className="text-[10px] text-slate-600">
            Waiting for file selection…
          </p>
        )}
      </div>
    </div>
  );
}

function AnalyzeTab() {
  const aiAnalysis = useAiStore((s) => s.aiAnalysis);
  const isAIStreaming = useAiStore((s) => s.isAIStreaming);

  if (!aiAnalysis && !isAIStreaming) {
    return (
      <EmptyPrompt
        icon={Sparkles}
        primary="No code analysis yet"
        secondary='Select code in the editor and click "Analyze Selection"'
        color="accent-gold"
      />
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-4 pt-3 pb-1 flex items-center gap-2">
        <SourceBadge source={aiAnalysis ? "ai" : null} isStreaming={isAIStreaming} />
      </div>
      <div className="px-4 py-3 ai-content">
        {aiAnalysis && (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{aiAnalysis}</ReactMarkdown>
        )}
        {isAIStreaming && <StreamCursor />}
      </div>
    </div>
  );
}

function BeginnerTab() {
  const sessionId = useSessionStore((s) => s.sessionId);
  const setSelectedFile = useSessionStore((s) => s.setSelectedFile);
  const setFileContent = useSessionStore((s) => s.setFileContent);

  const beginnerGuide = useAiStore((s) => s.beginnerGuide);
  const beginnerTopFiles = useAiStore((s) => s.beginnerTopFiles);
  const setBeginnerGuide = useAiStore((s) => s.setBeginnerGuide);

  const [content, setContent] = useState(beginnerGuide ?? "");
  const [isStreaming, setIsStreaming] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const didStreamRef = useRef(false);
  const ctrlRef = useRef<StreamControl | null>(null);

  useEffect(() => {
    if (beginnerGuide) setContent(beginnerGuide);
  }, [beginnerGuide]);

  useEffect(() => {
    if (!sessionId || didStreamRef.current || beginnerGuide) return;
    didStreamRef.current = true;
    setIsStreaming(true);

    let accumulated = "";
    const ctrl = streamAI(
      "/ai/beginner/stream",
      { session_id: sessionId },
      {
        onChunk: (text) => {
          accumulated += text;
          setContent(accumulated);
        },
        onDone: () => {
          setIsStreaming(false);
          ctrlRef.current = null;
          if (accumulated) {
            setBeginnerGuide(accumulated, [], "ai");
          }
        },
        onError: (err) => {
          setIsStreaming(false);
          ctrlRef.current = null;
          didStreamRef.current = false;
          let msg = err.message;
          try {
            const body = JSON.parse(msg.replace(/^HTTP \d+: /, ""));
            if (body?.detail?.error) msg = body.detail.error;
            else if (body?.detail) msg = String(body.detail);
          } catch {
            // use raw message
          }
          setErrorMsg(msg);
        },
      }
    );
    ctrlRef.current = ctrl;
    return () => {
      ctrl.cancel();
    };
  }, [sessionId, beginnerGuide, setBeginnerGuide]);

  const handleCancel = () => {
    ctrlRef.current?.cancel();
    setIsStreaming(false);
  };

  const handleFileClick = async (path: string) => {
    if (!sessionId) return;
    setSelectedFile(path);
    try {
      const fc = await getFileContent(sessionId, path);
      setFileContent(fc);
    } catch {
      
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-4 pt-3 pb-1 flex items-center gap-2 shrink-0">
        <SourceBadge source={content ? "ai" : null} isStreaming={isStreaming} />
        {!isStreaming && content && (
          <span className="text-[10px] text-slate-600">
            <BookOpen className="w-3 h-3 inline mr-1" />
            Onboarding Guide
          </span>
        )}
        {isStreaming && <CancelButton onClick={handleCancel} />}
      </div>

      {beginnerTopFiles.length > 0 && (
        <div className="px-4 py-2 border-b border-white/[0.04]">
          <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-2 font-semibold">
            Key Files
          </p>
          <div className="flex flex-wrap gap-1.5">
            {beginnerTopFiles.map((f) => (
              <button
                key={f.path}
                onClick={() => void handleFileClick(f.path)}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px]
                  bg-dark-800/60 border border-white/5 text-slate-300
                  hover:border-accent-gold/30 hover:text-accent-gold transition-all"
              >
                <FileCode2 className="w-3 h-3" />
                {f.path.split("/").pop() ?? f.path}
                <ChevronRight className="w-2.5 h-2.5 text-slate-600" />
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 py-3 ai-content">
        {errorMsg ? (
          <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-xs text-red-400">
            <X className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        ) : content ? (
          <>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
            {isStreaming && <StreamCursor />}
          </>
        ) : isStreaming ? (
          <div className="flex items-center gap-2 text-[11px] text-slate-500 mt-2">
            <StreamCursor />
            <span>Building onboarding guide…</span>
          </div>
        ) : (
          <EmptyPrompt
            icon={GraduationCap}
            primary="Beginner Guide"
            secondary="Analyse the repo first to generate your guide"
            color="purple-400"
          />
        )}
      </div>
    </div>
  );
}

interface StreamingEntry {
  question: string;
  answer: string;
  refs: Array<{ path: string; relevance_reason: string }>;
  timestamp: number;
}

function QATab() {
  const sessionId = useSessionStore((s) => s.sessionId);
  const setSelectedFile = useSessionStore((s) => s.setSelectedFile);
  const setFileContent = useSessionStore((s) => s.setFileContent);

  const qaHistory = useAiStore((s) => s.qaHistory);
  const addQAEntry = useAiStore((s) => s.addQAEntry);

  const [question, setQuestion] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [inProgress, setInProgress] = useState<StreamingEntry | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const ctrlRef = useRef<StreamControl | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [qaHistory, inProgress?.answer]);

  const handleAsk = () => {
    if (!question.trim() || !sessionId || isStreaming) return;
    const q = question.trim();
    setQuestion("");
    setIsStreaming(true);

    const entry: StreamingEntry = {
      question: q,
      answer: "",
      refs: [],
      timestamp: Date.now(),
    };
    setInProgress(entry);

    const ctrl = streamAI(
      "/ai/qa/stream",
      { session_id: sessionId, question: q },
      {
        onChunk: (text) => {
          setInProgress((prev) =>
            prev ? { ...prev, answer: prev.answer + text } : null
          );
        },
        onRefs: (refs) => {
          setInProgress((prev) => (prev ? { ...prev, refs } : null));
        },
        onDone: () => {
          setIsStreaming(false);
          ctrlRef.current = null;
          setInProgress((prev) => {
            if (prev) {
              addQAEntry(prev.question, prev.answer, prev.refs, "ai");
            }
            return null;
          });
        },
        onError: () => {
          setIsStreaming(false);
          ctrlRef.current = null;
          setInProgress((prev) => {
            if (prev) {
              const answer =
                prev.answer || "Failed to get answer. Please try again.";
              addQAEntry(prev.question, answer, prev.refs, "error");
            }
            return null;
          });
        },
      }
    );
    ctrlRef.current = ctrl;
  };

  const handleCancel = () => {
    ctrlRef.current?.cancel();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleAsk();
    }
  };

  const handleRefClick = async (path: string) => {
    if (!sessionId) return;
    setSelectedFile(path);
    try {
      const fc = await getFileContent(sessionId, path);
      setFileContent(fc);
    } catch {
      
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {qaHistory.length === 0 && !inProgress && (
          <div className="flex flex-col items-center justify-center text-center py-12">
            <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-3 bg-accent-cyan/10 border border-accent-cyan/12">
              <MessageCircleQuestion className="w-5 h-5 text-accent-cyan" />
            </div>
            <p className="text-xs text-slate-400 mb-2">
              Ask anything about the codebase
            </p>
            <div className="space-y-1">
              {[
                "How does the authentication work?",
                "Where are the API routes defined?",
                "What's the main entry point?",
              ].map((hint) => (
                <button
                  key={hint}
                  onClick={() => setQuestion(hint)}
                  className="block w-full text-left text-[11px] text-slate-500 px-3 py-1.5
                    rounded-md hover:bg-dark-800/60 hover:text-slate-300 transition-colors"
                >
                  &ldquo;{hint}&rdquo;
                </button>
              ))}
            </div>
          </div>
        )}

        {qaHistory.map((entry, i) => (
          <div key={i} className="space-y-3">
            <div className="flex justify-end">
              <div className="max-w-[85%] px-3 py-2 rounded-xl rounded-br-sm bg-accent-purple/15 border border-accent-purple/20">
                <p className="text-xs text-slate-200">{entry.question}</p>
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <SourceBadge source={entry.source} />
                <span className="text-[10px] text-slate-600 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {new Date(entry.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <div className="ai-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {entry.answer}
                </ReactMarkdown>
              </div>
              {entry.referenced_files.length > 0 && (
                <div className="mt-2 pt-2 border-t border-white/[0.04]">
                  <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5 font-semibold">
                    Referenced Files
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {entry.referenced_files.map((ref) => (
                      <button
                        key={ref.path}
                        onClick={() => void handleRefClick(ref.path)}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px]
                          bg-dark-800/60 border border-white/5 text-slate-400
                          hover:border-accent-cyan/30 hover:text-accent-cyan transition-all"
                        title={ref.relevance_reason}
                      >
                        <FileCode2 className="w-3 h-3" />
                        {ref.path.split("/").pop() ?? ref.path}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {inProgress && (
          <div className="space-y-3">
            <div className="flex justify-end">
              <div className="max-w-[85%] px-3 py-2 rounded-xl rounded-br-sm bg-accent-purple/15 border border-accent-purple/20">
                <p className="text-xs text-slate-200">{inProgress.question}</p>
              </div>
            </div>
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <SourceBadge source={null} isStreaming />
                <button
                  onClick={handleCancel}
                  className="ml-auto flex items-center gap-1 px-2 py-0.5 rounded text-[10px]
                    text-slate-400 hover:text-red-400 border border-white/5 hover:border-red-400/20 transition-colors"
                >
                  <X className="w-3 h-3" /> Stop
                </button>
              </div>
              <div className="ai-content">
                {inProgress.answer ? (
                  <>
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {inProgress.answer}
                    </ReactMarkdown>
                    <StreamCursor />
                  </>
                ) : (
                  <div className="flex items-center gap-2 text-[11px] text-slate-500">
                    <StreamCursor />
                    <span>Searching codebase…</span>
                  </div>
                )}
              </div>
              {inProgress.refs.length > 0 && (
                <div className="mt-2 pt-2 border-t border-white/[0.04]">
                  <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5 font-semibold">
                    Searching in
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {inProgress.refs.map((ref) => (
                      <button
                        key={ref.path}
                        onClick={() => void handleRefClick(ref.path)}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px]
                          bg-dark-800/60 border border-white/5 text-slate-400
                          hover:border-accent-cyan/30 hover:text-accent-cyan transition-all"
                      >
                        <FileCode2 className="w-3 h-3" />
                        {ref.path.split("/").pop() ?? ref.path}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="px-3 py-3 border-t border-white/[0.04] shrink-0">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about the codebase…"
            disabled={isStreaming}
            className="flex-1 px-3 py-2 rounded-lg bg-dark-800/60 border border-white/5
              text-xs text-white placeholder:text-slate-600
              focus:outline-none focus:border-accent-cyan/30
              disabled:opacity-50 transition-colors"
          />
          <button
            onClick={handleAsk}
            disabled={!question.trim() || isStreaming}
            className="p-2 rounded-lg bg-accent-cyan/15 border border-accent-cyan/20
              text-accent-cyan hover:bg-accent-cyan/25
              disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

const TABS: { id: AITab; label: string; icon: typeof Brain }[] = [
  { id: "explain", label: "Explain", icon: Brain },
  { id: "analyze", label: "Analyze", icon: Sparkles },
  { id: "beginner", label: "Guide", icon: GraduationCap },
  { id: "qa", label: "Q&A", icon: MessageCircleQuestion },
  { id: "advanced", label: "Advanced", icon: Rocket },
];

export function AIPanel() {
  const [activeTab, setActiveTab] = useState<AITab>("explain");
  const aiAnalysis = useAiStore((s) => s.aiAnalysis);
  const isAIStreaming = useAiStore((s) => s.isAIStreaming);
  const qaHistory = useAiStore((s) => s.qaHistory);

  useEffect(() => {
    const onShowAITab = (e: Event) => {
      const tab = (e as CustomEvent<AITab>).detail;
      if (tab) setActiveTab(tab);
    };
    const onShowAdvanced = (e: Event) => {
      setActiveTab("advanced");
      const detail = (e as CustomEvent).detail as unknown;
      if (detail) {
        setTimeout(() => {
          window.dispatchEvent(
            new CustomEvent("cmd:advanced-sub-tab", { detail })
          );
        }, 50);
      }
    };
    window.addEventListener("cmd:show-ai-tab", onShowAITab);
    window.addEventListener("cmd:show-advanced-ai", onShowAdvanced);
    return () => {
      window.removeEventListener("cmd:show-ai-tab", onShowAITab);
      window.removeEventListener("cmd:show-advanced-ai", onShowAdvanced);
    };
  }, []);

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="flex border-b border-white/[0.04] shrink-0 px-1">
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          const Icon = tab.icon;
          const hasNotif =
            (tab.id === "analyze" && !!aiAnalysis) ||
            (tab.id === "qa" && qaHistory.length > 0);
          const isTabStreaming = tab.id === "analyze" && isAIStreaming;

          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1 px-3 py-2 text-[10px] font-medium transition-colors relative
                ${
                  isActive
                    ? "text-accent-cyan border-b border-accent-cyan"
                    : "text-slate-500 hover:text-slate-300"
                }`}
            >
              <Icon className="w-3 h-3" />
              {tab.label}
              {isTabStreaming && (
                <span className="w-1.5 h-1.5 rounded-full bg-accent-cyan animate-ping ml-0.5" />
              )}
              {hasNotif && !isActive && (
                <div className="w-1.5 h-1.5 rounded-full bg-accent-gold absolute top-1.5 right-1" />
              )}
            </button>
          );
        })}
      </div>

      {activeTab === "explain" && <ExplainTab />}
      {activeTab === "analyze" && <AnalyzeTab />}
      {activeTab === "beginner" && <BeginnerTab />}
      {activeTab === "qa" && <QATab />}
      {activeTab === "advanced" && <AdvancedAIPanel />}
    </div>
  );
}
