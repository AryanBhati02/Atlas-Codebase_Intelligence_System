
import { useState } from "react";
import { motion } from "framer-motion";
import { GitBranch, Loader2, ArrowRight, AlertCircle } from "lucide-react";
import { ingestGitHub } from "../../api/ingest";
import { useAppStore } from "../../store/appStore";

export function GitHubInput() {
  const [url, setUrl] = useState("");
  const { isLoading, error, setLoading, setError, setSession, setShowIngestModal } = useAppStore();

  const isValidUrl = /^https?:\/\/(www\.)?github\.com\/[\w.-]+\/[\w.-]+/.test(
    url.trim()
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValidUrl || isLoading) return;

    setLoading(true);
    setError(null);

    try {
      const data = await ingestGitHub(url.trim());
      setLoading(false);
      setSession(data);
      setShowIngestModal(false);
    } catch (err: unknown) {
      setLoading(false);
      if (err && typeof err === "object" && "response" in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } };
        setError(axiosErr.response?.data?.detail || "Failed to clone repository.");
      } else {
        setError("Network error. Is the backend running on port 8000?");
      }
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-xs font-medium mb-2 uppercase tracking-wider" style={{ color: "var(--text-tertiary)" }}>
          Repository URL
        </label>
        <div className="relative">
          <GitBranch className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-muted)" }} />
          <input
            id="github-url-input"
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/owner/repo"
            disabled={isLoading}
            className="w-full pl-10 pr-4 py-3 rounded-xl
              text-sm
              focus:outline-none focus:border-accent-purple/50 focus:ring-1 focus:ring-accent-purple/20
              disabled:opacity-50 transition-all duration-200"
            style={{
              background: "var(--surface-input-bg)",
              border: "1px solid var(--surface-input-border)",
              color: "var(--text-primary)",
            }}
          />
        </div>
      </div>

      { }
      {error && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-start gap-2 p-3 rounded-lg bg-red-500/8 border border-red-500/15"
        >
          <AlertCircle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
          <p className="text-xs text-red-300 leading-relaxed">{error}</p>
        </motion.div>
      )}

      { }
      <button
        id="clone-button"
        type="submit"
        disabled={!isValidUrl || isLoading}
        className="w-full py-3 px-4 rounded-xl text-sm font-semibold
          bg-gradient-to-r from-accent-purple to-accent-violet
          text-white flex items-center justify-center gap-2
          hover:shadow-lg hover:shadow-accent-purple/20
          disabled:opacity-40 disabled:cursor-not-allowed
          transition-all duration-200 active:scale-[0.98]"
      >
        {isLoading ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Cloning Repository...
          </>
        ) : (
          <>
            Clone & Analyze
            <ArrowRight className="w-4 h-4" />
          </>
        )}
      </button>

      { }
      <p className="text-center text-xs" style={{ color: "var(--text-muted)" }}>
        Public repositories only · Shallow clone (depth=1) · Max 120s timeout
      </p>
    </form>
  );
}
