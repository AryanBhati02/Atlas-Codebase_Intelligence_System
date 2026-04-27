




import { useState, useCallback, useEffect } from "react";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  FileText,
  RefreshCw,
  Shield,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  Copy,
  Check,
  Cpu,
  Sparkles,
  GitPullRequest,
  Download,
  ShieldCheck,
} from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { generateReadme, getRefactorSuggestions, runSecurityScan, generatePRReview } from "../../api/api";

type AdvancedTab = "readme" | "refactor" | "security" | "pr-review";

function SourceBadge({ source }: { source: string | null }) {
  if (!source) return null;
  if (source === "ollama") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[9px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/15">
        <Cpu className="w-2.5 h-2.5" /> Local AI
      </span>
    );
  }
  if (source === "fallback") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[9px] font-medium bg-slate-500/10 text-slate-400 border border-slate-500/15">
        Template
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[9px] font-medium bg-accent-gold/10 text-accent-gold border border-accent-gold/15">
      <Sparkles className="w-2.5 h-2.5" /> AI
    </span>
  );
}



function ReadmeTab() {
  const {
    sessionId, readmeData, isReadmeLoading,
    setReadmeData, setReadmeLoading,
  } = useAppStore();
  const [copied, setCopied] = useState(false);

  const handleDownload = useCallback(() => {
    if (!readmeData?.readme) return;
    const blob = new Blob([readmeData.readme], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "README.md";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [readmeData]);

  const handleGenerate = useCallback(async () => {
    if (!sessionId || isReadmeLoading) return;
    setReadmeLoading(true);
    try {
      const data = await generateReadme(sessionId);
      setReadmeData(data);
    } catch {
      setReadmeLoading(false);
    }
  }, [sessionId, isReadmeLoading, setReadmeLoading, setReadmeData]);

  const handleCopy = useCallback(() => {
    if (readmeData?.readme) {
      navigator.clipboard.writeText(readmeData.readme);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [readmeData]);

  if (isReadmeLoading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 py-12">
        <Loader2 className="w-6 h-6 animate-spin text-accent-cyan/60" />
        <p className="text-[10px] animate-pulse" style={{ color: "var(--text-muted)" }}>Generating README from codebase…</p>
      </div>
    );
  }

  if (!readmeData) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-6 py-12">
        <div className="w-11 h-11 rounded-xl flex items-center justify-center mb-3"
          style={{ background: "var(--accent-cyan-subtle)", border: "1px solid var(--accent-cyan-subtle)" }}>
          <FileText className="w-5 h-5 text-accent-cyan/50" />
        </div>
        <p className="text-[11px] mb-1" style={{ color: "var(--text-secondary)" }}>Auto README Generator</p>
        <p className="text-[9px] mb-4" style={{ color: "var(--text-muted)" }}>Generate a professional README from your codebase structure</p>
        <motion.button
          onClick={handleGenerate}
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-[10px] font-medium
            bg-accent-cyan/[0.08] text-accent-cyan/80 border border-accent-cyan/15
            hover:bg-accent-cyan/15 transition-all duration-300"
        >
          <FileText className="w-3 h-3" /> Generate README
        </motion.button>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-3 pt-2 pb-1 flex items-center gap-2 shrink-0">
        <SourceBadge source={readmeData.source} />
        <div className="ml-auto flex items-center gap-1">
          <motion.button
            onClick={handleDownload}
            whileTap={{ scale: 0.9 }}
            className="flex items-center gap-1 px-2 py-1 rounded-md text-[9px] font-medium transition-colors"
            style={{
              color: "var(--accent-cyan)",
              background: "rgba(0, 200, 200, 0.08)",
              border: "1px solid rgba(0, 200, 200, 0.15)",
            }}
            title="Download as README.md"
          >
            <Download className="w-3 h-3" />
            Download
          </motion.button>
          <motion.button
            onClick={handleCopy}
            whileTap={{ scale: 0.9 }}
            className="p-1 rounded transition-colors"
            style={{ color: "var(--text-muted)" }}
            title="Copy to clipboard"
          >
            {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
          </motion.button>
          <motion.button
            onClick={handleGenerate}
            whileTap={{ scale: 0.9 }}
            className="p-1 rounded transition-colors"
            style={{ color: "var(--text-muted)" }}
            title="Regenerate"
          >
            <RefreshCw className="w-3 h-3" />
          </motion.button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-2 ai-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{readmeData.readme}</ReactMarkdown>
      </div>
    </div>
  );
}



function RefactorTab() {
  const {
    sessionId, selectedFile, refactorData, isRefactorLoading,
    setRefactorData, setRefactorLoading,
  } = useAppStore();

  const handleRefactor = useCallback(async () => {
    if (!sessionId || !selectedFile || isRefactorLoading) return;
    setRefactorLoading(true);
    try {
      const data = await getRefactorSuggestions(sessionId, selectedFile);
      setRefactorData(data);
    } catch {
      setRefactorLoading(false);
    }
  }, [sessionId, selectedFile, isRefactorLoading, setRefactorLoading, setRefactorData]);

  if (isRefactorLoading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 py-12">
        <Loader2 className="w-6 h-6 animate-spin text-accent-gold/60" />
        <p className="text-[10px] animate-pulse" style={{ color: "var(--text-muted)" }}>Analyzing refactor opportunities…</p>
      </div>
    );
  }

  if (!selectedFile) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-6 py-12">
        <div className="w-11 h-11 rounded-xl flex items-center justify-center mb-3"
          style={{ background: "var(--accent-gold-subtle)", border: "1px solid var(--accent-gold-subtle)" }}>
          <RefreshCw className="w-5 h-5 text-accent-gold/50" />
        </div>
        <p className="text-[11px] mb-1" style={{ color: "var(--text-secondary)" }}>Select a file first</p>
        <p className="text-[9px]" style={{ color: "var(--text-muted)" }}>Click a file to get refactoring suggestions</p>
      </div>
    );
  }

  if (!refactorData || refactorData.file_path !== selectedFile) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-6 py-12">
        <div className="w-11 h-11 rounded-xl flex items-center justify-center mb-3"
          style={{ background: "var(--accent-gold-subtle)", border: "1px solid var(--accent-gold-subtle)" }}>
          <RefreshCw className="w-5 h-5 text-accent-gold/50" />
        </div>
        <p className="text-[10px] mb-1 font-mono truncate max-w-[200px]" style={{ color: "var(--text-muted)" }}>{selectedFile}</p>
        <motion.button
          onClick={handleRefactor}
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-[10px] font-medium mt-3
            bg-accent-gold/[0.08] text-accent-gold/80 border border-accent-gold/15
            hover:bg-accent-gold/15 transition-all duration-300"
        >
          <RefreshCw className="w-3 h-3" /> Analyze Refactoring
        </motion.button>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-3 pt-2 pb-1 flex items-center gap-2 shrink-0">
        <SourceBadge source={refactorData.source} />
        <span className="text-[9px] font-mono truncate" style={{ color: "var(--text-muted)" }}>{refactorData.file_path}</span>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-2 ai-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{refactorData.suggestions}</ReactMarkdown>
      </div>
    </div>
  );
}



function SecurityTab() {
  const {
    sessionId, securityData, isSecurityLoading,
    setSecurityData, setSecurityLoading,
  } = useAppStore();

  const handleScan = useCallback(async () => {
    if (!sessionId || isSecurityLoading) return;
    setSecurityLoading(true);
    try {
      const data = await runSecurityScan(sessionId);
      setSecurityData(data);
    } catch {
      setSecurityLoading(false);
    }
  }, [sessionId, isSecurityLoading, setSecurityLoading, setSecurityData]);

  if (isSecurityLoading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 py-12">
        <Loader2 className="w-6 h-6 animate-spin text-red-400/60" />
        <p className="text-[10px] animate-pulse" style={{ color: "var(--text-muted)" }}>Scanning for security issues…</p>
      </div>
    );
  }

  if (!securityData) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-6 py-12">
        <div className="w-11 h-11 rounded-xl flex items-center justify-center mb-3"
          style={{ background: "rgba(239, 68, 68, 0.06)", border: "1px solid rgba(239, 68, 68, 0.1)" }}>
          <Shield className="w-5 h-5 text-red-400/50" />
        </div>
        <p className="text-[11px] mb-1" style={{ color: "var(--text-secondary)" }}>Security Scanner</p>
        <p className="text-[9px] mb-4" style={{ color: "var(--text-muted)" }}>Detect hardcoded secrets, injection risks, and vulnerabilities</p>
        <motion.button
          onClick={handleScan}
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-[10px] font-medium
            bg-red-500/[0.08] text-red-400/80 border border-red-500/15
            hover:bg-red-500/15 transition-all duration-300"
        >
          <Shield className="w-3 h-3" /> Run Security Scan
        </motion.button>
      </div>
    );
  }

  const { summary, findings, recommendations } = securityData;
  const scoreColor = summary.security_score >= 0.8 ? "text-emerald-400" :
    summary.security_score >= 0.5 ? "text-amber-400" : "text-red-400";

  const severityColors: Record<string, string> = {
    critical: "bg-red-500/15 text-red-400 border-red-500/20",
    high: "bg-orange-500/15 text-orange-400 border-orange-500/20",
    medium: "bg-amber-500/15 text-amber-400 border-amber-500/20",
    low: "bg-slate-500/15 text-slate-400 border-slate-500/20",
  };

  const priorityColors: Record<string, { bg: string; text: string; border: string }> = {
    critical: { bg: "rgba(239,68,68,0.06)", text: "#f87171", border: "rgba(239,68,68,0.15)" },
    high: { bg: "rgba(249,115,22,0.06)", text: "#fb923c", border: "rgba(249,115,22,0.15)" },
    medium: { bg: "rgba(245,158,11,0.06)", text: "#fbbf24", border: "rgba(245,158,11,0.15)" },
    low: { bg: "rgba(100,116,139,0.06)", text: "#94a3b8", border: "rgba(100,116,139,0.15)" },
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-3 py-2.5 shrink-0" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            {summary.total_findings === 0 ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-amber-400" />
            )}
            <span className="text-[11px] font-medium" style={{ color: "var(--text-primary)" }}>
              {summary.total_findings === 0 ? "No issues found" : `${summary.total_findings} findings`}
            </span>
          </div>
          <span className={`text-[11px] font-bold tabular-nums ${scoreColor}`}>
            {(summary.security_score * 100).toFixed(0)}%
          </span>
        </div>
        <div className="flex gap-1.5">
          {summary.critical > 0 && (
            <span className="px-1.5 py-0.5 rounded text-[8px] font-semibold bg-red-500/15 text-red-400">
              {summary.critical} CRITICAL
            </span>
          )}
          {summary.high > 0 && (
            <span className="px-1.5 py-0.5 rounded text-[8px] font-semibold bg-orange-500/15 text-orange-400">
              {summary.high} HIGH
            </span>
          )}
          {summary.medium > 0 && (
            <span className="px-1.5 py-0.5 rounded text-[8px] font-semibold bg-amber-500/15 text-amber-400">
              {summary.medium} MED
            </span>
          )}
          <span className="text-[8px] ml-auto" style={{ color: "var(--text-muted)" }}>
            {summary.files_scanned} files scanned
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {findings.length === 0 && (!recommendations || recommendations.length === 0) ? (
          <div className="flex flex-col items-center justify-center py-8">
            <CheckCircle2 className="w-8 h-8 text-emerald-400/40 mb-2" />
            <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>Your codebase looks secure!</p>
          </div>
        ) : (
          <div className="py-1">
            {findings.map((f, i) => (
              <div key={i} className="px-3 py-2 transition-colors" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                <div className="flex items-start gap-2">
                  <span className={`shrink-0 px-1.5 py-0.5 rounded text-[7px] font-bold uppercase border ${severityColors[f.severity] || severityColors.medium}`}>
                    {f.severity}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-[10px] font-medium" style={{ color: "var(--text-primary)" }}>{f.title}</p>
                    <p className="text-[9px] font-mono truncate mt-0.5" style={{ color: "var(--text-muted)" }}>{f.file}:{f.line}</p>
                    {f.fix && (
                      <p className="text-[9px] text-accent-cyan/60 mt-1">→ {f.fix}</p>
                    )}
                  </div>
                </div>
              </div>
            ))}

            {recommendations && recommendations.length > 0 && (
              <div className="px-3 pt-3 pb-2">
                <div className="flex items-center gap-1.5 mb-2">
                  <ShieldCheck className="w-3.5 h-3.5" style={{ color: "var(--accent-cyan)" }} />
                  <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: "var(--text-tertiary)" }}>
                    Security Recommendations
                  </span>
                </div>
                <div className="space-y-2">
                  {recommendations.map((rec, i) => {
                    const pc = priorityColors[rec.priority] || priorityColors.medium;
                    return (
                      <div
                        key={i}
                        className="rounded-lg overflow-hidden"
                        style={{ background: pc.bg, border: `1px solid ${pc.border}` }}
                      >
                        <div className="px-3 py-2">
                          <div className="flex items-center gap-2 mb-1">
                            <span
                              className="px-1.5 py-0.5 rounded text-[7px] font-bold uppercase"
                              style={{ background: pc.border, color: pc.text }}
                            >
                              {rec.priority}
                            </span>
                            <span className="text-[10px] font-medium" style={{ color: pc.text }}>
                              {rec.title}
                            </span>
                          </div>
                          <p className="text-[9px] mb-1.5" style={{ color: "var(--text-muted)" }}>
                            {rec.description}
                          </p>
                          {rec.steps && rec.steps.length > 0 && (
                            <ul className="space-y-0.5">
                              {rec.steps.map((step, si) => (
                                <li key={si} className="text-[9px] flex items-start gap-1.5" style={{ color: "var(--text-secondary)" }}>
                                  <span className="text-[8px] font-mono mt-0.5" style={{ color: pc.text }}>{si + 1}.</span>
                                  {step}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}



function PRReviewTab() {
  const {
    sessionId, selectedFile, prReviewData, isPRReviewLoading,
    setPRReviewData, setPRReviewLoading,
  } = useAppStore();
  const [copied, setCopied] = useState(false);

  const handleGenerate = useCallback(async () => {
    if (!sessionId || isPRReviewLoading) return;
    setPRReviewLoading(true);
    try {
      const filePaths = selectedFile ? [selectedFile] : [];
      const data = await generatePRReview(sessionId, filePaths);
      setPRReviewData(data);
    } catch {
      setPRReviewLoading(false);
    }
  }, [sessionId, selectedFile, isPRReviewLoading, setPRReviewLoading, setPRReviewData]);

  const handleCopy = useCallback(() => {
    if (prReviewData?.review) {
      navigator.clipboard.writeText(prReviewData.review);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [prReviewData]);

  if (isPRReviewLoading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 py-12">
        <Loader2 className="w-6 h-6 animate-spin text-accent-purple/60" />
        <p className="text-[10px] animate-pulse" style={{ color: "var(--text-muted)" }}>Generating PR review…</p>
      </div>
    );
  }

  if (!prReviewData) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-center px-6 py-12">
        <div className="w-11 h-11 rounded-xl flex items-center justify-center mb-3"
          style={{ background: "var(--accent-purple-subtle)", border: "1px solid var(--accent-purple-border)" }}>
          <GitPullRequest className="w-5 h-5 text-accent-purple/50" />
        </div>
        <p className="text-[11px] mb-1" style={{ color: "var(--text-secondary)" }}>PR Review Generator</p>
        <p className="text-[9px] mb-1" style={{ color: "var(--text-muted)" }}>
          {selectedFile
            ? `Review selected file: ${selectedFile.split("/").pop()}`
            : "Full repository review — risk, impact, per-file notes"}
        </p>
        <p className="text-[8px] mb-4" style={{ color: "var(--text-muted)" }}>
          Uses dependency graph + dead code analysis for context
        </p>
        <motion.button
          onClick={handleGenerate}
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-[10px] font-medium
            bg-accent-purple/[0.08] text-accent-purple/80 border border-accent-purple/15
            hover:bg-accent-purple/15 transition-all duration-300"
        >
          <GitPullRequest className="w-3 h-3" /> Generate Review
        </motion.button>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-3 pt-2 pb-1 flex items-center gap-2 shrink-0">
        <SourceBadge source={prReviewData.source} />
        <div className="ml-auto flex items-center gap-1">
          <motion.button
            onClick={handleCopy}
            whileTap={{ scale: 0.9 }}
            className="p-1 rounded transition-colors"
            style={{ color: "var(--text-muted)" }}
            title="Copy to clipboard"
          >
            {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
          </motion.button>
          <motion.button
            onClick={handleGenerate}
            whileTap={{ scale: 0.9 }}
            className="p-1 rounded transition-colors"
            style={{ color: "var(--text-muted)" }}
            title="Regenerate"
          >
            <RefreshCw className="w-3 h-3" />
          </motion.button>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-2 ai-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{prReviewData.review}</ReactMarkdown>
      </div>
    </div>
  );
}




const ADVANCED_TABS: { id: AdvancedTab; label: string; icon: typeof FileText }[] = [
  { id: "readme", label: "README", icon: FileText },
  { id: "refactor", label: "Refactor", icon: RefreshCw },
  { id: "security", label: "Security", icon: Shield },
  { id: "pr-review", label: "PR Review", icon: GitPullRequest },
];

export function AdvancedAIPanel() {
  const [tab, setTab] = useState<AdvancedTab>("readme");


  useEffect(() => {
    const onSubTab = (e: Event) => {
      const detail = (e as CustomEvent).detail as string;
      const tabMap: Record<string, AdvancedTab> = {
        readme: "readme",
        refactor: "refactor",
        security: "security",
        pr: "pr-review",
        "pr-review": "pr-review",
      };
      const target = tabMap[detail];
      if (target) setTab(target);
    };
    window.addEventListener("cmd:advanced-sub-tab", onSubTab);
    return () => window.removeEventListener("cmd:advanced-sub-tab", onSubTab);
  }, []);

  return (
    <div className="flex-1 flex flex-col min-h-0">
      { }
      <div className="flex shrink-0 px-1" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
        {ADVANCED_TABS.map((t) => {
          const Icon = t.icon;
          const active = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-1 px-2.5 py-1.5 text-[9px] font-medium transition-all duration-200`}
              style={{ color: active ? "var(--text-primary)" : "var(--text-muted)" }}
            >
              <Icon className="w-2.5 h-2.5" />
              {t.label}
              {active && (
                <motion.div
                  layoutId="adv-tab-ind"
                  className="absolute bottom-0 left-1 right-1 h-px"
                  style={{ background: "linear-gradient(90deg, transparent, rgba(124,110,224,0.4), transparent)" }}
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
            </button>
          );
        })}
      </div>

      {tab === "readme" && <ReadmeTab />}
      {tab === "refactor" && <RefactorTab />}
      {tab === "security" && <SecurityTab />}
      {tab === "pr-review" && <PRReviewTab />}
    </div>
  );
}
