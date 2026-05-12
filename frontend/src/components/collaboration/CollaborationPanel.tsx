import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  MessageSquare,
  Send,
  Loader2,
  CheckCircle2,
  Trash2,
  Share2,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useAppStore } from "../../store/appStore";
import {
  postComment,
  getComments,
  getCommentCounts,
  resolveComment as apiResolveComment,
  deleteComment as apiDeleteComment,
  getShareToken,
} from "../../api/api";

export function CollaborationPanel() {
  const {
    sessionId,
    selectedFile,
    comments,
    isCommentsLoading,
    setComments,
    addComment,
    removeComment,
    updateComment,
    setCommentCounts,
    setCommentsLoading,
  } = useAppStore();

  const [message, setMessage] = useState("");
  const [author, setAuthor] = useState("Anonymous");
  const [isSending, setIsSending] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!sessionId || !selectedFile) return;
    let cancelled = false;
    (async () => {
      setCommentsLoading(true);
      try {
        const data = await getComments(sessionId, selectedFile);
        if (!cancelled) setComments(data);
      } catch {
        if (!cancelled) setCommentsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [sessionId, selectedFile, setComments, setCommentsLoading]);

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

  const handleSubmit = useCallback(async () => {
    if (!sessionId || !selectedFile || !message.trim()) return;
    setIsSending(true);
    try {
      const comment = await postComment(
        sessionId, "file", selectedFile, message.trim(), author
      );
      addComment(comment);
      setMessage("");
      inputRef.current?.focus();
    } catch { }
    finally { setIsSending(false); }
  }, [sessionId, selectedFile, message, author, addComment]);

  const handleResolve = useCallback(async (commentId: string) => {
    if (!sessionId) return;
    try {
      const updated = await apiResolveComment(sessionId, commentId);
      updateComment(updated);
    } catch { }
  }, [sessionId, updateComment]);

  const handleDelete = useCallback(async (commentId: string) => {
    if (!sessionId) return;
    removeComment(commentId);
    try {
      await apiDeleteComment(sessionId, commentId);
    } catch { }
  }, [sessionId, removeComment]);

  const handleShare = useCallback(async () => {
    if (!sessionId) return;
    try {
      const data = await getShareToken(sessionId);
      const url = `${window.location.origin}${data.share_url}`;
      setShareUrl(url);
    } catch { }
  }, [sessionId]);

  const handleCopy = useCallback(() => {
    if (!shareUrl) return;
    navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [shareUrl]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  if (!selectedFile) {
    return (
      <div className="p-4 text-center">
        <MessageSquare className="w-5 h-5 text-slate-600 mx-auto mb-2" />
        <p className="text-[10px] text-slate-600">
          Select a file to view comments
        </p>
      </div>
    );
  }

  const fileName = selectedFile.split("/").pop() || selectedFile;
  const fileComments = comments.filter((c) => c.target_id === selectedFile);

  return (
    <div className="flex flex-col h-full">
      { }
      <div
        className="flex items-center gap-2 px-3 py-2 border-b border-white/[0.04] cursor-pointer
          hover:bg-white/[0.01] transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <MessageSquare className="w-3.5 h-3.5 text-accent-purple/70" />
        <span className="text-[10px] font-semibold text-slate-300">
          Comments
        </span>
        {fileComments.length > 0 && (
          <span className="text-[8px] bg-accent-purple/10 text-accent-purple/70
            px-1.5 py-0.5 rounded-full font-semibold">
            {fileComments.length}
          </span>
        )}
        <span className="text-[8px] text-slate-600 truncate ml-auto mr-1">
          {fileName}
        </span>

        { }
        <button
          onClick={(e) => { e.stopPropagation(); handleShare(); }}
          className="p-1 rounded hover:bg-white/[0.04] text-slate-600 hover:text-accent-cyan transition-colors"
          title="Share session"
        >
          <Share2 className="w-3 h-3" />
        </button>

        {expanded ? (
          <ChevronUp className="w-3 h-3 text-slate-700" />
        ) : (
          <ChevronDown className="w-3 h-3 text-slate-700" />
        )}
      </div>

      { }
      <AnimatePresence>
        {shareUrl && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-accent-cyan/[0.04]
              border-b border-accent-cyan/[0.08]">
              <input
                type="text"
                readOnly
                value={shareUrl}
                className="flex-1 text-[9px] bg-transparent text-accent-cyan/70 outline-none
                  font-mono truncate"
              />
              <button
                onClick={handleCopy}
                className="p-1 rounded hover:bg-white/[0.04] transition-colors"
              >
                {copied ? (
                  <Check className="w-3 h-3 text-emerald-400" />
                ) : (
                  <Copy className="w-3 h-3 text-slate-500" />
                )}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="flex-1 flex flex-col overflow-hidden"
          >
            { }
            <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
              {isCommentsLoading ? (
                <div className="flex items-center gap-2 py-4 justify-center">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-600" />
                  <span className="text-[9px] text-slate-600">Loading…</span>
                </div>
              ) : fileComments.length === 0 ? (
                <div className="text-center py-4">
                  <p className="text-[9px] text-slate-700">No comments yet</p>
                </div>
              ) : (
                fileComments.map((c) => (
                  <motion.div
                    key={c.id}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    className={`relative group rounded-lg px-2.5 py-2 transition-all duration-200
                      ${c.resolved
                        ? "bg-white/[0.01] opacity-50"
                        : "bg-white/[0.02] hover:bg-white/[0.03]"
                      } border border-white/[0.03]`}
                  >
                    { }
                    <div className="flex items-center gap-1.5 mb-1">
                      <div className="w-4 h-4 rounded-full bg-accent-purple/15 flex items-center
                        justify-center shrink-0">
                        <span className="text-[7px] font-bold text-accent-purple/70">
                          {c.author.charAt(0).toUpperCase()}
                        </span>
                      </div>
                      <span className="text-[9px] font-semibold text-slate-400">
                        {c.author}
                      </span>
                      <span className="text-[7px] text-slate-700 ml-auto">
                        {formatTimeAgo(c.created_at)}
                      </span>
                    </div>

                    { }
                    <p className={`text-[10px] leading-relaxed ml-5.5
                      ${c.resolved ? "text-slate-600 line-through" : "text-slate-300"}`}>
                      {c.message}
                    </p>

                    { }
                    <div className="absolute top-1.5 right-1.5 flex items-center gap-0.5
                      opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => handleResolve(c.id)}
                        className={`p-0.5 rounded transition-colors
                          ${c.resolved ? "text-emerald-400" : "text-slate-600 hover:text-emerald-400"}`}
                        title={c.resolved ? "Unresolve" : "Resolve"}
                      >
                        <CheckCircle2 className="w-3 h-3" />
                      </button>
                      <button
                        onClick={() => handleDelete(c.id)}
                        className="p-0.5 rounded text-slate-600 hover:text-red-400 transition-colors"
                        title="Delete"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  </motion.div>
                ))
              )}
            </div>

            { }
            <div className="px-3 py-2 border-t border-white/[0.04]">
              { }
              <div className="flex items-center gap-1 mb-1.5">
                <span className="text-[8px] text-slate-700">As:</span>
                <input
                  type="text"
                  value={author}
                  onChange={(e) => setAuthor(e.target.value)}
                  className="flex-1 text-[9px] bg-transparent text-slate-400 outline-none
                    border-b border-transparent focus:border-accent-purple/20 transition-colors"
                  placeholder="Your name"
                />
              </div>

              { }
              <div className="flex items-end gap-1.5">
                <textarea
                  ref={inputRef}
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Add a comment…"
                  rows={1}
                  className="flex-1 resize-none text-[10px] bg-white/[0.02] rounded-lg
                    px-2.5 py-1.5 text-slate-300 placeholder:text-slate-700
                    border border-white/[0.04] focus:border-accent-purple/20
                    outline-none transition-colors"
                />
                <button
                  onClick={handleSubmit}
                  disabled={!message.trim() || isSending}
                  className="p-1.5 rounded-lg bg-accent-purple/10 text-accent-purple/70
                    hover:bg-accent-purple/15 disabled:opacity-30 disabled:cursor-not-allowed
                    transition-all"
                >
                  {isSending ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Send className="w-3.5 h-3.5" />
                  )}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function formatTimeAgo(ts: string): string {
  try {
    const date = new Date(ts);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    if (days < 30) return `${days}d ago`;
    return `${Math.floor(days / 30)}mo ago`;
  } catch {
    return "";
  }
}
