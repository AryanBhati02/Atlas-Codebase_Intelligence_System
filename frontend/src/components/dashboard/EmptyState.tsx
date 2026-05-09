import { useState } from "react";
import { motion } from "framer-motion";
import { GitBranch, Clock, ExternalLink, Loader2, AlertCircle } from "lucide-react";
import { useUiStore } from "../../store/uiStore";
import { useSessionStore } from "../../store/sessionStore";
import type { RecentRepo } from "../../store/uiStore";
import { ingestGitHub, checkSession } from "../../api/ingest";

const CLONE_TIMEOUT_MS = 120_000;

export function EmptyState() {
    const recentRepos = useUiStore((s) => s.recentRepos);
    const setShowIngestModal = useUiStore((s) => s.setShowIngestModal);
    const setSessionAndLoading = useSessionStore((s) => s.setSessionAndLoading);
    const setError = useSessionStore((s) => s.setError);

    const [loadingUrl, setLoadingUrl] = useState<string | null>(null);
    const [recentError, setRecentError] = useState<{ url: string; message: string } | null>(null);

    const handleRecentClick = async (repo: RecentRepo) => {
        if (repo.sourceType !== "github" || !repo.url) {
            setShowIngestModal(true);
            return;
        }

        setLoadingUrl(repo.url);
        setRecentError(null);
        setError(null);

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), CLONE_TIMEOUT_MS);

        try {
            const isValid = await checkSession(repo.url);
            if (!isValid) {
                clearTimeout(timeoutId);
                setLoadingUrl(null);
                setRecentError({
                    url: repo.url,
                    message: "Session expired — re-clone to analyze.",
                });
                return;
            }

            const data = await ingestGitHub(repo.url, controller.signal);
            clearTimeout(timeoutId);
            setSessionAndLoading(data);
        } catch (err: unknown) {
            clearTimeout(timeoutId);

            let message = "Failed to clone repository.";

            if (err instanceof DOMException && err.name === "AbortError") {
                message = "Clone timed out after 120 seconds — try again.";
            } else if (err && typeof err === "object" && "response" in err) {
                const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } };
                const status = axiosErr.response?.status;
                if (status === 404 || status === 410) {
                    message = "Session expired — re-clone to analyze.";
                } else {
                    message = axiosErr.response?.data?.detail ?? message;
                }
            } else if (err instanceof Error) {
                message = err.message || message;
            }

            setRecentError({ url: repo.url, message });
        } finally {
            setLoadingUrl(null);
        }
    };

    return (
        <div className="empty-state-center">
            <motion.div
                initial={{ opacity: 0, y: -12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, ease: [0.22, 0.61, 0.36, 1] }}
                className="text-center mb-10"
            >
                <div className="flex items-center justify-center gap-3 mb-4">
                    <motion.div
                        className="w-10 h-10 rounded-xl flex items-center justify-center overflow-hidden shadow-sm"
                        animate={{ rotate: [0, 3, -3, 0] }}
                        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
                    >
                        <img src="/icon.png" alt="Logo" className="w-full h-full object-cover" />
                    </motion.div>
                </div>
                <h2
                    className="text-3xl md:text-4xl font-extrabold mb-3 tracking-tight"
                    style={{
                        background: "linear-gradient(180deg, var(--text-primary) 0%, var(--text-secondary) 100%)",
                        WebkitBackgroundClip: "text",
                        WebkitTextFillColor: "transparent",
                    }}
                >
                    Codebase Intelligence
                </h2>
                <p
                    className="text-[15px] font-medium max-w-md mx-auto leading-relaxed"
                    style={{ color: "var(--text-tertiary)" }}
                >
                    Transform any repository into an interactive, AI-powered knowledge
                    system. Understand unfamiliar code in minutes.
                </p>
            </motion.div>

            {recentRepos.length > 0 && (
                <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.2, duration: 0.4 }}
                    className="w-full max-w-md"
                >
                    <div className="flex items-center gap-2 mb-3">
                        <Clock className="w-3.5 h-3.5" style={{ color: "var(--text-tertiary)" }} />
                        <span
                            className="text-[10px] font-semibold uppercase tracking-wider"
                            style={{ color: "var(--text-tertiary)" }}
                        >
                            Recent
                        </span>
                    </div>

                    <div className="space-y-2">
                        {recentRepos.map((repo, i) => {
                            const hasError = recentError?.url === repo.url;
                            return (
                                <div key={repo.url}>
                                    <motion.button
                                        initial={{ opacity: 0, x: -8 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ delay: 0.3 + i * 0.05 }}
                                        className="recent-item w-full"
                                        onClick={() => handleRecentClick(repo)}
                                        disabled={loadingUrl !== null}
                                        style={{ opacity: loadingUrl && loadingUrl !== repo.url ? 0.5 : 1 }}
                                    >
                                        {loadingUrl === repo.url ? (
                                            <Loader2 className="w-4 h-4 shrink-0 animate-spin" style={{ color: "var(--accent-purple)" }} />
                                        ) : (
                                            <GitBranch className="w-4 h-4 shrink-0" style={{ color: "var(--accent-cyan)" }} />
                                        )}
                                        <div className="flex-1 min-w-0 text-left">
                                            <div
                                                className="text-[12px] font-medium truncate"
                                                style={{ color: "var(--text-primary)" }}
                                            >
                                                {repo.name}
                                            </div>
                                            <div
                                                className="text-[10px] truncate"
                                                style={{ color: "var(--text-muted)" }}
                                            >
                                                {loadingUrl === repo.url ? "Cloning repository…" : repo.url}
                                            </div>
                                        </div>
                                        {loadingUrl !== repo.url && (
                                            <>
                                                <span className="text-[9px] shrink-0" style={{ color: "var(--text-faint)" }}>
                                                    {formatTimeAgo(repo.lastOpened)}
                                                </span>
                                                <ExternalLink className="w-3 h-3 shrink-0" style={{ color: "var(--text-faint)" }} />
                                            </>
                                        )}
                                    </motion.button>

                                    {hasError && (
                                        <motion.div
                                            initial={{ opacity: 0, y: -4 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            className="flex items-start gap-2 mt-1 px-3 py-2 rounded-lg bg-red-500/8 border border-red-500/15"
                                        >
                                            <AlertCircle className="w-3.5 h-3.5 text-red-400 mt-0.5 shrink-0" />
                                            <p className="text-[11px] text-red-300 leading-relaxed">{recentError.message}</p>
                                        </motion.div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </motion.div>
            )}
        </div>
    );
}

function formatTimeAgo(ts: number): string {
    const diffMs = Date.now() - ts;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return "today";
    if (diffDays === 1) return "yesterday";
    if (diffDays < 30) return `${diffDays}d ago`;
    return `${Math.floor(diffDays / 30)}mo ago`;
}
