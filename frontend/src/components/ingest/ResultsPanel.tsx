import { useMemo } from "react";
import { motion } from "framer-motion";
import {
  CheckCircle2,
  FileCode2,
  FolderTree,
  GitBranch,
  Upload,
  RotateCcw,
  Hash,
  HardDrive,
} from "lucide-react";
import { useAppStore } from "../../store/appStore";

const LANG_COLORS: Record<string, string> = {
  Python: "bg-blue-500/15 text-blue-300",
  JavaScript: "bg-amber-500/15 text-amber-300",
  TypeScript: "bg-sky-500/15 text-sky-300",
  Java: "bg-orange-500/15 text-orange-300",
  Go: "bg-cyan-500/15 text-cyan-300",
  Rust: "bg-red-500/15 text-red-300",
  "C++": "bg-pink-500/15 text-pink-300",
  C: "bg-slate-500/15 text-slate-300",
  HTML: "bg-rose-500/15 text-rose-300",
  CSS: "bg-violet-500/15 text-violet-300",
  JSON: "bg-emerald-500/15 text-emerald-300",
  Markdown: "bg-gray-500/15 text-gray-300",
  YAML: "bg-lime-500/15 text-lime-300",
  Shell: "bg-green-500/15 text-green-300",
  Ruby: "bg-red-500/15 text-red-400",
  PHP: "bg-indigo-500/15 text-indigo-300",
};

function getLangColor(lang: string | null): string {
  if (!lang) return "bg-white/5 text-slate-400";
  return LANG_COLORS[lang] ?? "bg-white/5 text-slate-400";
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ResultsPanel() {
  const { repoName, files, totalFiles, sourceType, reset } = useAppStore();

  const languageStats = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const f of files) {
      const lang = f.language ?? "Other";
      counts[lang] = (counts[lang] || 0) + 1;
    }
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);
  }, [files]);

  const totalSize = useMemo(
    () => files.reduce((sum, f) => sum + f.size_bytes, 0),
    [files]
  );

  return (
    <div className="min-h-screen flex flex-col items-center px-4 py-12">
      { }
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: "spring", stiffness: 300, damping: 25 }}
        className="text-center mb-8"
      >
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", delay: 0.1, stiffness: 400, damping: 15 }}
          className="w-14 h-14 rounded-2xl bg-emerald-500/15 border border-emerald-500/20
            flex items-center justify-center mx-auto mb-4"
        >
          <CheckCircle2 className="w-7 h-7 text-emerald-400" />
        </motion.div>

        <h1 className="text-2xl font-bold mb-1" style={{ color: "var(--text-primary)" }}>Repository Loaded</h1>
        <div className="flex items-center justify-center gap-2 text-sm" style={{ color: "var(--text-tertiary)" }}>
          {sourceType === "github" ? (
            <GitBranch className="w-3.5 h-3.5" />
          ) : (
            <Upload className="w-3.5 h-3.5" />
          )}
          <span className="font-medium" style={{ color: "var(--text-secondary)" }}>{repoName}</span>
        </div>
      </motion.div>

      { }
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="grid grid-cols-3 gap-3 w-full max-w-lg mb-6"
      >
        <StatCard
          icon={<FileCode2 className="w-4 h-4" />}
          label="Files"
          value={totalFiles.toString()}
          delay={0.25}
        />
        <StatCard
          icon={<Hash className="w-4 h-4" />}
          label="Languages"
          value={languageStats.length.toString()}
          delay={0.3}
        />
        <StatCard
          icon={<HardDrive className="w-4 h-4" />}
          label="Total Size"
          value={formatBytes(totalSize)}
          delay={0.35}
        />
      </motion.div>

      { }
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35 }}
        className="glass-card rounded-2xl w-full max-w-lg p-5 mb-4"
      >
        <h2 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: "var(--text-tertiary)" }}>
          Language Distribution
        </h2>
        <div className="flex flex-wrap gap-2">
          {languageStats.map(([lang, count], i) => (
            <motion.span
              key={lang}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.4 + i * 0.04 }}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium ${getLangColor(lang)}`}
            >
              {lang}
              <span className="opacity-60">{count}</span>
            </motion.span>
          ))}
        </div>
      </motion.div>

      { }
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.45 }}
        className="glass-card rounded-2xl w-full max-w-lg overflow-hidden"
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-white/5">
          <div className="flex items-center gap-2">
            <FolderTree className="w-4 h-4 text-accent-purple" />
            <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--text-tertiary)" }}>
              Files ({totalFiles})
            </h2>
          </div>
        </div>

        <div className="max-h-72 overflow-y-auto">
          {files.map((file, i) => (
            <motion.div
              key={file.path}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.5 + Math.min(i, 30) * 0.02 }}
              className="flex items-center gap-3 px-5 py-2.5 hover:bg-white/[0.02] transition-colors"
            >
              <FileCode2 className="w-3.5 h-3.5 text-slate-600 shrink-0" />
              <span className="text-sm truncate flex-1 font-mono text-xs" style={{ color: "var(--text-secondary)" }}>
                {file.path}
              </span>
              {file.language && (
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0 ${getLangColor(file.language)}`}
                >
                  {file.language}
                </span>
              )}
              <span className="text-[10px] shrink-0 tabular-nums" style={{ color: "var(--text-muted)" }}>
                {formatBytes(file.size_bytes)}
              </span>
            </motion.div>
          ))}
        </div>
      </motion.div>

      { }
      <motion.button
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.7 }}
        onClick={reset}
        className="mt-6 flex items-center gap-2 px-4 py-2 rounded-xl
          text-sm text-slate-400 hover:text-white
          bg-dark-800/40 hover:bg-dark-700/60 border border-white/5
          transition-all duration-200"
      >
        <RotateCcw className="w-3.5 h-3.5" />
        Load Another Repository
      </motion.button>

      { }
      <p className="mt-4 text-xs text-slate-700 text-center">
        Phase 1 — Ingest Complete · Parse, Graph, and AI features coming next
      </p>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  delay,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  delay: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay }}
      className="glass-card rounded-xl p-4 text-center"
    >
      <div className="flex items-center justify-center text-accent-purple mb-2">
        {icon}
      </div>
      <p className="text-lg font-bold" style={{ color: "var(--text-primary)" }}>{value}</p>
      <p className="text-[10px] uppercase tracking-wider mt-0.5" style={{ color: "var(--text-muted)" }}>
        {label}
      </p>
    </motion.div>
  );
}
