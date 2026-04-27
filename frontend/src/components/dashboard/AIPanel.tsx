





import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Brain,
  Sparkles,
  Loader2,
  Cpu,
  GraduationCap,
  MessageCircleQuestion,
  Send,
  FileCode2,
  ChevronRight,
  BookOpen,
  Clock,
  Rocket,
} from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { getBeginnerGuide, askQuestion, getFileContent, explainFile } from "../../api/api";
import { AdvancedAIPanel } from "./AdvancedAIPanel";

type AITab = "explain" | "analyze" | "beginner" | "qa" | "advanced";

function SourceBadge({ source }: { source: string | null }) {
  if (!source) return null;
  if (source === "ollama") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/15">
        <Cpu className="w-3 h-3" />
        Ollama AI
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium bg-accent-gold/10 text-accent-gold border border-accent-gold/15">
      <Sparkles className="w-3 h-3" />
      Smart Analysis
    </span>
  );
}

function LoadingState({ message }: { message: string }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-3 py-12">
      <div className="relative">
        <div className="w-12 h-12 rounded-2xl bg-accent-cyan/10 border border-accent-cyan/20 flex items-center justify-center">
          <Brain className="w-5 h-5 text-accent-cyan" />
        </div>
        <Loader2 className="w-4 h-4 animate-spin text-accent-gold absolute -top-1 -right-1" />
      </div>
      <p className="text-xs text-slate-400 animate-pulse">{message}</p>
      <div className="flex gap-1 mt-2">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-accent-cyan/40 animate-bounce"
            style={{ animationDelay: `${i * 0.15}s` }}
          />
        ))}
      </div>
    </div>
  );
}

function ShimmerBlock() {
  return (
    <div className="space-y-3 px-4 py-4">
      <div className="shimmer h-4 rounded w-3/4" />
      <div className="shimmer h-3 rounded w-full" />
      <div className="shimmer h-3 rounded w-5/6" />
      <div className="shimmer h-3 rounded w-2/3" />
      <div className="shimmer h-20 rounded w-full mt-4" />
      <div className="shimmer h-3 rounded w-4/5" />
      <div className="shimmer h-3 rounded w-3/4" />
    </div>
  );
}




function ExplainTab() {
  const { aiExplanation, aiSource, isAILoading, selectedFile } = useAppStore();

  if (isAILoading) return <LoadingState message="Analyzing file structure…" />;

  if (!aiExplanation) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-6 py-12">
        <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-3 bg-accent-cyan/10 border border-accent-cyan/12">
          <Brain className="w-5 h-5 text-accent-cyan" />
        </div>
        <p className="text-xs text-slate-400 mb-1">No explanation yet</p>
        <p className="text-[10px] text-slate-600">
          Select a file to get an AI-powered explanation
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-4 pt-3 pb-1 flex items-center gap-2">
        <SourceBadge source={aiSource} />
        {selectedFile && (
          <span className="text-[10px] text-slate-600 truncate font-mono">{selectedFile}</span>
        )}
      </div>
      <div className="px-4 py-3 ai-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{aiExplanation}</ReactMarkdown>
      </div>
    </div>
  );
}




function AnalyzeTab() {
  const { aiAnalysis, aiSource, isAILoading } = useAppStore();

  if (isAILoading) return <LoadingState message="Reviewing code quality…" />;

  if (!aiAnalysis) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-6 py-12">
        <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-3 bg-accent-gold/10 border border-accent-gold/12">
          <Sparkles className="w-5 h-5 text-accent-gold" />
        </div>
        <p className="text-xs text-slate-400 mb-1">No code analysis yet</p>
        <p className="text-[10px] text-slate-600">
          Select code in the editor and click "Analyze Selection"
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-4 pt-3 pb-1 flex items-center gap-2">
        <SourceBadge source={aiSource} />
      </div>
      <div className="px-4 py-3 ai-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{aiAnalysis}</ReactMarkdown>
      </div>
    </div>
  );
}




function BeginnerTab() {
  const {
    sessionId,
    beginnerGuide,
    beginnerTopFiles,
    beginnerSource,
    isBeginnerLoading,
    setBeginnerGuide,
    setBeginnerLoading,
    setSelectedFile,
    setFileContent,
    setAIExplanation,
    setAILoading,
  } = useAppStore();

  useEffect(() => {
    if (beginnerGuide || isBeginnerLoading || !sessionId) return;

    let cancelled = false;
    (async () => {
      setBeginnerLoading(true);
      try {
        const data = await getBeginnerGuide(sessionId);
        if (!cancelled) {
          setBeginnerGuide(data.guide, data.top_files, data.source);
        }
      } catch {
        if (!cancelled) setBeginnerLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [sessionId, beginnerGuide, isBeginnerLoading, setBeginnerGuide, setBeginnerLoading]);

  const handleFileClick = async (path: string) => {
    if (!sessionId) return;
    setSelectedFile(path);
    try {
      const content = await getFileContent(sessionId, path);
      setFileContent(content);
    } catch { }
    try {
      setAILoading(true);
      const ai = await explainFile(sessionId, path);
      setAIExplanation(ai.explanation, ai.source);
    } catch { }
    finally { setAILoading(false); }
  };

  if (isBeginnerLoading) {
    return (
      <div className="flex-1 flex flex-col">
        <LoadingState message="Generating onboarding guide…" />
        <ShimmerBlock />
      </div>
    );
  }

  if (!beginnerGuide) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-6 py-12">
        <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-3 bg-purple-500/10 border border-purple-500/12">
          <GraduationCap className="w-5 h-5 text-purple-400" />
        </div>
        <p className="text-xs text-slate-400 mb-1">Beginner Guide</p>
        <p className="text-[10px] text-slate-600">
          Loading your personalized onboarding guide…
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-4 pt-3 pb-1 flex items-center gap-2">
        <SourceBadge source={beginnerSource} />
        <span className="text-[10px] text-slate-600">
          <BookOpen className="w-3 h-3 inline mr-1" />
          Onboarding Guide
        </span>
      </div>

      { }
      {beginnerTopFiles.length > 0 && (
        <div className="px-4 py-2 border-b border-white/[0.04]">
          <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-2 font-semibold">
            Key Files
          </p>
          <div className="flex flex-wrap gap-1.5">
            {beginnerTopFiles.map((f) => (
              <button
                key={f.path}
                onClick={() => handleFileClick(f.path)}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[10px]
                  bg-dark-800/60 border border-white/5 text-slate-300
                  hover:border-accent-gold/30 hover:text-accent-gold transition-all"
              >
                <FileCode2 className="w-3 h-3" />
                {f.path.split("/").pop()}
                <ChevronRight className="w-2.5 h-2.5 text-slate-600" />
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="px-4 py-3 ai-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{beginnerGuide}</ReactMarkdown>
      </div>
    </div>
  );
}




function QATab() {
  const {
    sessionId,
    qaHistory,
    isQALoading,
    addQAEntry,
    setQALoading,
    setSelectedFile,
    setFileContent,
    setAIExplanation,
    setAILoading,
  } = useAppStore();

  const [question, setQuestion] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [qaHistory]);

  const handleAsk = async () => {
    if (!question.trim() || !sessionId || isQALoading) return;
    const q = question.trim();
    setQuestion("");
    setQALoading(true);

    try {
      const data = await askQuestion(sessionId, q);
      addQAEntry(q, data.answer, data.referenced_files, data.source);
    } catch {
      addQAEntry(q, "Failed to get answer. Please try again.", [], "error");
    }
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
      const content = await getFileContent(sessionId, path);
      setFileContent(content);
    } catch { }
    try {
      setAILoading(true);
      const ai = await explainFile(sessionId, path);
      setAIExplanation(ai.explanation, ai.source);
    } catch { }
    finally { setAILoading(false); }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      { }
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {qaHistory.length === 0 && !isQALoading && (
          <div className="flex flex-col items-center justify-center text-center py-12">
            <div className="w-12 h-12 rounded-2xl flex items-center justify-center mb-3 bg-accent-cyan/10 border border-accent-cyan/12">
              <MessageCircleQuestion className="w-5 h-5 text-accent-cyan" />
            </div>
            <p className="text-xs text-slate-400 mb-2">Ask anything about the codebase</p>
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
                  "{hint}"
                </button>
              ))}
            </div>
          </div>
        )}

        {qaHistory.map((entry, i) => (
          <div key={i} className="space-y-3">
            { }
            <div className="flex justify-end">
              <div className="qa-question max-w-[85%] px-3 py-2 rounded-xl rounded-br-sm bg-accent-purple/15 border border-accent-purple/20">
                <p className="text-xs text-slate-200">{entry.question}</p>
              </div>
            </div>

            { }
            <div className="qa-answer">
              <div className="flex items-center gap-2 mb-1.5">
                <SourceBadge source={entry.source} />
                <span className="text-[10px] text-slate-600 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {new Date(entry.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <div className="ai-content">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{entry.answer}</ReactMarkdown>
              </div>

              { }
              {entry.referenced_files.length > 0 && (
                <div className="mt-2 pt-2 border-t border-white/[0.04]">
                  <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5 font-semibold">
                    Referenced Files
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {entry.referenced_files.map((ref) => (
                      <button
                        key={ref.path}
                        onClick={() => handleRefClick(ref.path)}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px]
                          bg-dark-800/60 border border-white/5 text-slate-400
                          hover:border-accent-cyan/30 hover:text-accent-cyan transition-all"
                        title={ref.relevance_reason}
                      >
                        <FileCode2 className="w-3 h-3" />
                        {ref.path.split("/").pop()}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {isQALoading && <LoadingState message="Searching codebase…" />}
      </div>

      { }
      <div className="px-3 py-3 border-t border-white/[0.04] shrink-0">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about the codebase…"
            disabled={isQALoading}
            className="flex-1 px-3 py-2 rounded-lg bg-dark-800/60 border border-white/5
              text-xs text-white placeholder:text-slate-600
              focus:outline-none focus:border-accent-cyan/30
              disabled:opacity-50 transition-colors"
          />
          <button
            onClick={handleAsk}
            disabled={!question.trim() || isQALoading}
            className="p-2 rounded-lg bg-accent-cyan/15 border border-accent-cyan/20
              text-accent-cyan hover:bg-accent-cyan/25
              disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          >
            {isQALoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
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
  const { isAILoading, aiAnalysis, qaHistory, isQALoading } = useAppStore();


  useEffect(() => {
    const onShowAITab = (e: Event) => {
      const tab = (e as CustomEvent).detail as AITab;
      if (tab) setActiveTab(tab);
    };
    const onShowAdvanced = (e: Event) => {
      setActiveTab("advanced");

      const detail = (e as CustomEvent).detail;
      if (detail) {
        setTimeout(() => {
          window.dispatchEvent(new CustomEvent("cmd:advanced-sub-tab", { detail }));
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
      { }
      <div className="flex border-b border-white/[0.04] shrink-0 px-1">
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          const Icon = tab.icon;
          const hasNotif =
            (tab.id === "analyze" && !!aiAnalysis) ||
            (tab.id === "qa" && qaHistory.length > 0);
          const isTabLoading =
            (tab.id === "explain" && isAILoading) ||
            (tab.id === "qa" && isQALoading);

          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1 px-3 py-2 text-[10px] font-medium transition-colors relative
                ${isActive
                  ? "text-accent-cyan border-b border-accent-cyan"
                  : "text-slate-500 hover:text-slate-300"
                }`}
            >
              <Icon className="w-3 h-3" />
              {tab.label}
              {isTabLoading && (
                <Loader2 className="w-2.5 h-2.5 animate-spin ml-0.5" />
              )}
              {hasNotif && !isActive && (
                <div className="w-1.5 h-1.5 rounded-full bg-accent-gold absolute top-1.5 right-1" />
              )}
            </button>
          );
        })}
      </div>

      { }
      {activeTab === "explain" && <ExplainTab />}
      {activeTab === "analyze" && <AnalyzeTab />}
      {activeTab === "beginner" && <BeginnerTab />}
      {activeTab === "qa" && <QATab />}
      {activeTab === "advanced" && <AdvancedAIPanel />}
    </div>
  );
}
