





import { useState, useCallback, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  GitCommit,
  ChevronDown,
  ChevronUp,
  Loader2,
  FilePlus2,
  FileMinus2,
  FileEdit,
  BarChart3,
  X,
} from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { getGitTimeline, getCommitDiff, getCoverage } from "../../api/api";

export function GitTimeline() {
  const {
    sessionId,
    timelineData,
    isTimelineLoading,
    selectedCommit,
    commitDiff,
    isCommitDiffLoading,
    coverageData,
    isCoverageLoading,
    showCoverage,
    setTimelineData,
    setTimelineLoading,
    setSelectedCommit,
    setCommitDiff,
    setCommitDiffLoading,
    setCoverageData,
    setCoverageLoading,
    toggleCoverage,
    setHighlightedFiles,
  } = useAppStore();

  const [expanded, setExpanded] = useState(false);
  const [sliderValue, setSliderValue] = useState(0);
  const sliderRef = useRef<HTMLInputElement>(null);


  useEffect(() => {
    if (!sessionId || timelineData || isTimelineLoading) return;
    let cancelled = false;
    (async () => {
      setTimelineLoading(true);
      try {
        const data = await getGitTimeline(sessionId);
        if (!cancelled) setTimelineData(data);
      } catch {
        if (!cancelled) setTimelineLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [sessionId, timelineData, isTimelineLoading, setTimelineData, setTimelineLoading]);


  useEffect(() => {
    if (!sessionId || coverageData || isCoverageLoading) return;
    let cancelled = false;
    (async () => {
      setCoverageLoading(true);
      try {
        const data = await getCoverage(sessionId);
        if (!cancelled) setCoverageData(data);
      } catch {
        if (!cancelled) setCoverageLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [sessionId, coverageData, isCoverageLoading, setCoverageData, setCoverageLoading]);


  const handleSliderChange = useCallback(
    async (value: number) => {
      if (!sessionId || !timelineData || timelineData.commits.length === 0) return;
      setSliderValue(value);
      const commit = timelineData.commits[value];
      if (!commit) return;
      setSelectedCommit(commit);


      setCommitDiffLoading(true);
      try {
        const diff = await getCommitDiff(sessionId, commit.hash);
        setCommitDiff(diff);
      } catch {
        setCommitDiffLoading(false);
      }
    },
    [sessionId, timelineData, setSelectedCommit, setCommitDiff, setCommitDiffLoading]
  );


  const handleClear = useCallback(() => {
    setSelectedCommit(null);
    setCommitDiff(null);
    setHighlightedFiles(new Set());
  }, [setSelectedCommit, setCommitDiff, setHighlightedFiles]);


  if (!sessionId) return null;

  const commits = timelineData?.commits ?? [];
  const hasCommits = commits.length > 0;
  const isLoaded = !!timelineData && !isTimelineLoading;

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4, delay: 0.3 }}
      className="absolute top-3 left-3 z-20 w-[320px] max-h-[calc(100vh-140px)] flex flex-col pointer-events-none"
    >
      <div className="rounded-xl flex flex-col min-h-0 pointer-events-auto shadow-2xl backdrop-blur-xl"
        style={{
          background: "var(--bg-overlay)",
          border: "1px solid var(--border-subtle)",
        }}>

        { }
        <div
          className="flex items-center gap-2 px-3 py-2 cursor-pointer
            hover:bg-white/[0.02] transition-colors"
          onClick={() => setExpanded(!expanded)}
        >
          <GitCommit className="w-3.5 h-3.5 text-accent-cyan/70" />
          <span className="text-[10px] font-semibold" style={{ color: "var(--text-secondary)" }}>
            Git Timeline
          </span>

          {isTimelineLoading && (
            <Loader2 className="w-3 h-3 animate-spin text-accent-cyan/50 ml-1" />
          )}

          {isLoaded && !hasCommits && (
            <span className="text-[9px] ml-auto mr-2" style={{ color: "var(--text-muted)" }}>
              No git history available
            </span>
          )}

          {hasCommits && (
            <span className="text-[9px] ml-auto mr-2" style={{ color: "var(--text-muted)" }}>
              {commits.length} commits
            </span>
          )}

          { }
          {coverageData?.has_coverage && (
            <button
              onClick={(e) => { e.stopPropagation(); toggleCoverage(); }}
              className={`flex items-center gap-1 px-2 py-0.5 rounded text-[8px] font-medium
                transition-all duration-200 mr-1
                ${showCoverage
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                  : "bg-white/[0.02] text-slate-600 border border-white/[0.04]"
                }`}
            >
              <BarChart3 className="w-2.5 h-2.5" />
              Coverage
            </button>
          )}

          {expanded ? (
            <ChevronDown className="w-3 h-3" style={{ color: "var(--text-muted)" }} />
          ) : (
            <ChevronUp className="w-3 h-3" style={{ color: "var(--text-muted)" }} />
          )}
        </div>

        { }
        {hasCommits && (
          <div className="px-3 pb-2">
            <input
              ref={sliderRef}
              type="range"
              min={0}
              max={commits.length - 1}
              value={sliderValue}
              onChange={(e) => handleSliderChange(Number(e.target.value))}
              className="timeline-slider w-full h-1 rounded-full appearance-none cursor-pointer
                bg-white/[0.04] accent-cyan-400"
              style={{
                background: hasCommits
                  ? `linear-gradient(to right, rgba(34,211,238,0.3) ${(sliderValue / Math.max(commits.length - 1, 1)) * 100}%, rgba(255,255,255,0.04) 0%)`
                  : undefined,
              }}
            />

            { }
            {selectedCommit && (
              <div className="flex items-center gap-2 mt-1.5">
                <code className="text-[9px] text-accent-cyan/60 font-mono">
                  {selectedCommit.short_hash}
                </code>
                <span className="text-[9px] truncate flex-1" style={{ color: "var(--text-muted)" }}>
                  {selectedCommit.message}
                </span>
                <span className="text-[8px]" style={{ color: "var(--text-muted)" }}>
                  {formatTimestamp(selectedCommit.timestamp)}
                </span>
                <button
                  onClick={handleClear}
                  className="p-0.5 rounded transition-colors"
                  style={{ color: "var(--text-muted)" }}
                >
                  <X className="w-2.5 h-2.5" />
                </button>
              </div>
            )}
          </div>
        )}

        { }
        <AnimatePresence>
          {expanded && hasCommits && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className="overflow-hidden"
            >
              <div style={{ borderTop: "1px solid var(--border-subtle)" }} className="flex-1 overflow-y-auto min-h-0">
                {commits.map((c, i) => (
                  <button
                    key={c.hash}
                    onClick={() => { setSliderValue(i); handleSliderChange(i); }}
                    className={`w-full flex items-center gap-2 px-3 py-1.5 text-left
                      transition-all duration-150
                      ${selectedCommit?.hash === c.hash
                        ? "bg-accent-cyan/[0.06] border-l-2 border-accent-cyan/30"
                        : "hover:bg-white/[0.02] border-l-2 border-transparent"
                      }`}
                  >
                    <code className="text-[8px] text-accent-cyan/50 font-mono shrink-0">
                      {c.short_hash}
                    </code>
                    <span className="text-[9px] truncate flex-1" style={{ color: "var(--text-secondary)" }}>
                      {c.message}
                    </span>
                    <span className="text-[8px] shrink-0" style={{ color: "var(--text-muted)" }}>
                      {c.files_changed?.length || 0} files
                    </span>
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        { }
        <AnimatePresence>
          {commitDiff && commitDiff.files.length > 0 && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div className="px-3 py-2" style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <p className="text-[8px] uppercase tracking-wider font-semibold mb-1.5" style={{ color: "var(--text-muted)" }}>
                  Changed Files
                </p>
                {isCommitDiffLoading ? (
                  <div className="flex items-center gap-2 py-2">
                    <Loader2 className="w-3 h-3 animate-spin" style={{ color: "var(--text-muted)" }} />
                    <span className="text-[9px]" style={{ color: "var(--text-muted)" }}>Loading diff…</span>
                  </div>
                ) : (
                  <div className="space-y-0.5 max-h-32 overflow-y-auto">
                    {commitDiff.files.map((f) => (
                      <div key={f.path} className="flex items-center gap-1.5 py-0.5">
                        <FileStatusIcon status={f.status} />
                        <span className="text-[9px] truncate flex-1" style={{ color: "var(--text-secondary)" }}>
                          {f.path}
                        </span>
                        {(f.additions > 0 || f.deletions > 0) && (
                          <span className="text-[8px] shrink-0">
                            {f.additions > 0 && (
                              <span className="text-emerald-500">+{f.additions}</span>
                            )}
                            {f.deletions > 0 && (
                              <span className="text-red-400 ml-1">-{f.deletions}</span>
                            )}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}



function FileStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "A":
      return <FilePlus2 className="w-2.5 h-2.5 text-emerald-400 shrink-0" />;
    case "D":
      return <FileMinus2 className="w-2.5 h-2.5 text-red-400 shrink-0" />;
    default:
      return <FileEdit className="w-2.5 h-2.5 text-amber-400 shrink-0" />;
  }
}

function formatTimestamp(ts: string): string {
  try {
    const date = new Date(ts);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return "today";
    if (diffDays === 1) return "1d ago";
    if (diffDays < 30) return `${diffDays}d ago`;
    if (diffDays < 365) return `${Math.floor(diffDays / 30)}mo ago`;
    return `${Math.floor(diffDays / 365)}y ago`;
  } catch {
    return "";
  }
}
