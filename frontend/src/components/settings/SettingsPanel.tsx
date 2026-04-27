import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Settings,
  Cpu,
  Cloud,
  Activity,
  RefreshCw,
  Check,
  AlertTriangle,
  Loader2,
  Trash2,
  ShieldCheck,
  ToggleLeft,
  ToggleRight,
  HardDrive,
  Database,
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { useSettingsStore } from "../../store/settingsStore";
import {
  getAIStatus,
  updateProviderKey,
  testProvider,
  clearAICache,
} from "../../api/api";
import type { ProviderInfo } from "../../types";

const PROVIDER_META: Record<
  string,
  { label: string; color: string; description: string }
> = {
  ollama: {
    label: "Ollama (Local)",
    color: "#22c55e",
    description: "Local inference — no API key needed",
  },
  groq: {
    label: "Groq",
    color: "#f59e0b",
    description: "14,400 req/day free — Llama 3 8B",
  },
  gemini: {
    label: "Google Gemini",
    color: "#3b82f6",
    description: "1,500 req/day free — Gemini 1.5 Flash",
  },
  mistral: {
    label: "Mistral",
    color: "#8b5cf6",
    description: "~1,000 req/day — Mistral 7B",
  },
  huggingface: {
    label: "HuggingFace",
    color: "#f97316",
    description: "~500 req/day — Various models",
  },
};

function StatusDot({ status }: { status: string }) {
  let color = "#6b7280";
  if (status === "online" || status === "valid") color = "#22c55e";
  else if (status === "rate_limited") color = "#f59e0b";
  else if (status === "offline" || status === "invalid") color = "#ef4444";
  else if (status === "no_key") color = "#6b7280";

  return (
    <div className="relative flex items-center">
      <div
        className="w-2 h-2 rounded-full"
        style={{ backgroundColor: color }}
      />
      {(status === "online" || status === "valid") && (
        <div
          className="absolute w-2 h-2 rounded-full animate-ping"
          style={{ backgroundColor: color, opacity: 0.4 }}
        />
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, { bg: string; text: string; border: string }> = {
    online: { bg: "rgba(16,185,129,0.1)", text: "#34d399", border: "rgba(16,185,129,0.2)" },
    valid: { bg: "rgba(16,185,129,0.1)", text: "#34d399", border: "rgba(16,185,129,0.2)" },
    offline: { bg: "rgba(239,68,68,0.1)", text: "#f87171", border: "rgba(239,68,68,0.2)" },
    invalid: { bg: "rgba(239,68,68,0.1)", text: "#f87171", border: "rgba(239,68,68,0.2)" },
    rate_limited: { bg: "rgba(245,158,11,0.1)", text: "#fbbf24", border: "rgba(245,158,11,0.2)" },
    no_key: { bg: "var(--surface-card-bg)", text: "var(--text-muted)", border: "var(--surface-card-border)" },
    unknown: { bg: "var(--surface-card-bg)", text: "var(--text-muted)", border: "var(--surface-card-border)" },
  };

  const labels: Record<string, string> = {
    online: "✅ Connected",
    valid: "✅ Valid",
    offline: "❌ Offline",
    invalid: "❌ Invalid",
    rate_limited: "⚠️ Rate Limited",
    no_key: "⚠️ Not Set",
    unknown: "Unknown",
  };

  const c = colorMap[status] || colorMap.unknown;

  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wider"
      style={{
        background: c.bg,
        color: c.text,
        border: `1px solid ${c.border}`,
      }}
    >
      {labels[status] || status}
    </span>
  );
}

function ProviderKeyRow({
  provider,
  onKeyUpdated,
}: {
  provider: ProviderInfo;
  onKeyUpdated: () => void;
}) {
  const meta = PROVIDER_META[provider.name];
  const [keyInput, setKeyInput] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    valid: boolean;
    latency_ms: number;
    error: string | null;
  } | null>(null);
  const [expanded, setExpanded] = useState(false);

  if (!meta) return null;

  const handleSaveTest = async () => {
    if (!keyInput.trim()) return;
    setIsTesting(true);
    setTestResult(null);

    try {
      const result = await updateProviderKey(provider.name, keyInput.trim());
      setTestResult(result);
      if (result.valid) {
        setKeyInput("");
        onKeyUpdated();
      }
    } catch {
      setTestResult({
        valid: false,
        latency_ms: 0,
        error: "Failed to connect to backend.",
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleTest = async () => {
    setIsTesting(true);
    setTestResult(null);
    try {
      const result = await testProvider(provider.name);
      setTestResult({
        valid: result.available,
        latency_ms: result.latency_ms,
        error: result.error,
      });
    } catch {
      setTestResult({
        valid: false,
        latency_ms: 0,
        error: "Connection failed.",
      });
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl overflow-hidden"
      style={{
        background: "var(--surface-card-bg)",
        border: "1px solid var(--surface-card-border)",
      }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 transition-colors"
        style={{ background: "transparent" }}
        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface-card-hover)")}
        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
      >
        <StatusDot status={provider.status} />
        <div
          className="w-1.5 h-5 rounded-full shrink-0"
          style={{ backgroundColor: meta.color + "40" }}
        />
        <div className="flex-1 text-left">
          <p className="text-xs font-medium" style={{ color: "var(--text-primary)" }}>{meta.label}</p>
          <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>{meta.description}</p>
        </div>
        <StatusBadge status={provider.status} />
        {expanded ? (
          <ChevronUp className="w-3 h-3" style={{ color: "var(--text-muted)" }} />
        ) : (
          <ChevronDown className="w-3 h-3" style={{ color: "var(--text-muted)" }} />
        )}
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div
              className="px-4 pb-4 space-y-3 pt-3"
              style={{ borderTop: "1px solid var(--surface-section-border)" }}
            >
              {provider.key_set && (
                <div className="flex items-center gap-2">
                  <span className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                    Current key:
                  </span>
                  <code
                    className="text-[10px] px-2 py-0.5 rounded font-mono"
                    style={{
                      color: "var(--text-tertiary)",
                      background: "var(--surface-input-bg)",
                    }}
                  >
                    {provider.key_masked}
                  </code>
                </div>
              )}

              <div className="flex items-center gap-4">
                <div className="flex items-center gap-1 text-[10px]" style={{ color: "var(--text-muted)" }}>
                  <Activity className="w-3 h-3" />
                  {provider.requests_today} req today
                </div>
                {provider.avg_latency_ms > 0 && (
                  <div className="flex items-center gap-1 text-[10px]" style={{ color: "var(--text-muted)" }}>
                    <RefreshCw className="w-3 h-3" />
                    {provider.avg_latency_ms}ms avg
                  </div>
                )}
                <div className="flex items-center gap-1 text-[10px]" style={{ color: "var(--text-muted)" }}>
                  <HardDrive className="w-3 h-3" />
                  {provider.model}
                </div>
              </div>

              {provider.key_required && (
                <div className="space-y-2">
                  <div className="relative">
                    <input
                      type={showKey ? "text" : "password"}
                      value={keyInput}
                      onChange={(e) => setKeyInput(e.target.value)}
                      placeholder={`Enter ${meta.label} API key…`}
                      className="w-full px-3 py-2 pr-20 rounded-lg text-xs font-mono focus:outline-none transition-colors"
                      style={{
                        background: "var(--surface-input-bg)",
                        border: "1px solid var(--surface-input-border)",
                        color: "var(--text-primary)",
                      }}
                    />
                    <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-1">
                      <button
                        onClick={() => setShowKey(!showKey)}
                        className="p-1 rounded transition-colors"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {showKey ? (
                          <EyeOff className="w-3 h-3" />
                        ) : (
                          <Eye className="w-3 h-3" />
                        )}
                      </button>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleSaveTest}
                      disabled={!keyInput.trim() || isTesting}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium
                        bg-accent-purple/12 text-accent-purple border border-accent-purple/20
                        hover:bg-accent-purple/18 disabled:opacity-30 transition-all"
                    >
                      {isTesting ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <ShieldCheck className="w-3 h-3" />
                      )}
                      Save & Test
                    </button>
                    {provider.key_set && (
                      <button
                        onClick={handleTest}
                        disabled={isTesting}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium disabled:opacity-30 transition-all"
                        style={{
                          background: "var(--surface-card-bg)",
                          color: "var(--text-tertiary)",
                          border: "1px solid var(--surface-input-border)",
                        }}
                      >
                        <RefreshCw className="w-3 h-3" />
                        Re-test
                      </button>
                    )}
                  </div>
                </div>
              )}

              {!provider.key_required && (
                <button
                  onClick={handleTest}
                  disabled={isTesting}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-medium
                    bg-emerald-500/10 text-emerald-400 border border-emerald-500/20
                    hover:bg-emerald-500/15 disabled:opacity-30 transition-all"
                >
                  {isTesting ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <RefreshCw className="w-3 h-3" />
                  )}
                  Test Connection
                </button>
              )}

              <AnimatePresence>
                {testResult && (
                  <motion.div
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg text-[11px]"
                    style={{
                      background: testResult.valid ? "rgba(16,185,129,0.08)" : "rgba(239,68,68,0.08)",
                      border: `1px solid ${testResult.valid ? "rgba(16,185,129,0.15)" : "rgba(239,68,68,0.15)"}`,
                      color: testResult.valid ? "#34d399" : "#f87171",
                    }}
                  >
                    {testResult.valid ? (
                      <>
                        <Check className="w-3.5 h-3.5" />
                        <span>
                          Valid — {testResult.latency_ms}ms latency
                        </span>
                      </>
                    ) : (
                      <>
                        <AlertTriangle className="w-3.5 h-3.5" />
                        <span>{testResult.error || "Validation failed"}</span>
                      </>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export function SettingsPanel() {
  const { settingsPanelOpen, setSettingsPanelOpen, sessionId } = useAppStore();
  const {
    settings, ollamaModels, isLoadingModels, ollamaReachable,
    draft, isDirty, isApplying, applyError,
    loadSettings, loadOllamaModels, updateDraft, applyDraft, cancelDraft,
  } = useSettingsStore();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isClearingCache, setIsClearingCache] = useState(false);
  const [cacheCleared, setCacheCleared] = useState(false);

  useEffect(() => {
    if (settingsPanelOpen) {
      loadSettings();
      loadOllamaModels();
    }
  }, [settingsPanelOpen, loadSettings, loadOllamaModels]);

  const handleRefreshAll = async () => {
    setIsRefreshing(true);
    try {
      const status = await getAIStatus();
      useAppStore.getState().setAIStatus(status);
      await loadSettings();
    } catch {
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleClearCache = async () => {
    setIsClearingCache(true);
    setCacheCleared(false);
    try {
      await clearAICache(sessionId || undefined);
      setCacheCleared(true);
      await loadSettings();
      setTimeout(() => setCacheCleared(false), 3000);
    } catch {
    } finally {
      setIsClearingCache(false);
    }
  };

  const handleApply = async () => {
    const ok = await applyDraft();
    if (ok) {
      const status = await getAIStatus();
      useAppStore.getState().setAIStatus(status);
    }
  };

  const handleCancel = () => {
    cancelDraft();
  };

  return (
    <AnimatePresence>
      {settingsPanelOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="settings-backdrop"
            onClick={() => setSettingsPanelOpen(false)}
          />

          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{
              type: "spring",
              stiffness: 300,
              damping: 30,
            }}
            className="settings-panel"
          >
            <div
              className="flex items-center justify-between px-5 py-4"
              style={{ borderBottom: "1px solid var(--surface-section-border)" }}
            >
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-lg bg-accent-purple/12 border border-accent-purple/20 flex items-center justify-center">
                  <Settings className="w-3.5 h-3.5 text-accent-purple" />
                </div>
                <div>
                  <h2 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>Settings</h2>
                  <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>
                    AI providers & configuration
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSettingsPanelOpen(false)}
                className="p-1.5 rounded-lg transition-colors"
                style={{ color: "var(--text-muted)" }}
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto">
              <div
                className="px-5 py-4"
                style={{ borderBottom: "1px solid var(--surface-section-border)" }}
              >
                <div className="flex items-center justify-between mb-3">
                  <h3
                    className="text-[11px] font-semibold uppercase tracking-wider"
                    style={{ color: "var(--text-tertiary)" }}
                  >
                    AI Status
                  </h3>
                  <button
                    onClick={handleRefreshAll}
                    disabled={isRefreshing}
                    className="flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium disabled:opacity-30 transition-all"
                    style={{
                      color: "var(--text-muted)",
                      background: "var(--surface-card-bg)",
                      border: "1px solid var(--surface-card-border)",
                    }}
                  >
                    <RefreshCw
                      className={`w-3 h-3 ${isRefreshing ? "animate-spin" : ""}`}
                    />
                    Refresh
                  </button>
                </div>

                <div className="grid grid-cols-5 gap-2">
                  {settings?.providers.map((p, i) => {
                    const meta = PROVIDER_META[p.name];
                    if (!meta) return null;
                    return (
                      <motion.div
                        key={p.name}
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.05 }}
                        className="flex flex-col items-center gap-1.5 p-2 rounded-lg"
                        style={{
                          background: "var(--surface-card-bg)",
                          border: "1px solid var(--surface-card-border)",
                        }}
                      >
                        <StatusDot status={p.status} />
                        <span
                          className="text-[9px] text-center leading-tight"
                          style={{ color: "var(--text-muted)" }}
                        >
                          {p.name === "ollama"
                            ? "Local"
                            : p.name.charAt(0).toUpperCase() +
                            p.name.slice(1)}
                        </span>
                      </motion.div>
                    );
                  })}
                </div>

                {settings && (
                  <div
                    className="mt-3 flex items-center gap-2 px-3 py-2 rounded-lg"
                    style={{
                      background: "var(--surface-card-bg)",
                      border: "1px solid var(--surface-card-border)",
                    }}
                  >
                    <Cpu className="w-3 h-3" style={{ color: "var(--accent-cyan)" }} />
                    <span className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>
                      Active model:
                    </span>
                    <span
                      className="text-[10px] font-medium font-mono"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {settings.active_model}
                    </span>
                  </div>
                )}
              </div>

              <div
                className="px-5 py-4"
                style={{ borderBottom: "1px solid var(--surface-section-border)" }}
              >
                <h3
                  className="text-[11px] font-semibold uppercase tracking-wider mb-3"
                  style={{ color: "var(--text-tertiary)" }}
                >
                  API Key Manager
                </h3>
                <div className="space-y-2">
                  {settings?.providers.map((p) => (
                    <ProviderKeyRow
                      key={p.name}
                      provider={p}
                      onKeyUpdated={loadSettings}
                    />
                  ))}
                </div>
              </div>

              <div
                className="px-5 py-4"
                style={{ borderBottom: "1px solid var(--surface-section-border)" }}
              >
                <h3
                  className="text-[11px] font-semibold uppercase tracking-wider mb-3"
                  style={{ color: "var(--text-tertiary)" }}
                >
                  Model Selection
                </h3>

                <div className="space-y-3">
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label
                        className="text-[10px]"
                        style={{ color: "var(--text-muted)" }}
                      >
                        Local Model (Ollama)
                      </label>
                      <button
                        onClick={loadOllamaModels}
                        disabled={isLoadingModels}
                        className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium disabled:opacity-30 transition-all"
                        style={{
                          color: "var(--text-muted)",
                          background: "var(--surface-card-bg)",
                          border: "1px solid var(--surface-card-border)",
                        }}
                      >
                        <RefreshCw className={`w-2.5 h-2.5 ${isLoadingModels ? "animate-spin" : ""}`} />
                        Refresh
                      </button>
                    </div>
                    <select
                      value={draft.selectedModel}
                      onChange={(e) => updateDraft({ selectedModel: e.target.value })}
                      className="w-full px-3 py-2 rounded-lg text-xs focus:outline-none focus:border-accent-purple/30 transition-colors appearance-none cursor-pointer"
                      style={{
                        background: "var(--surface-input-bg)",
                        border: "1px solid var(--surface-input-border)",
                        color: "var(--text-primary)",
                      }}
                    >
                      {ollamaModels.length > 0 ? (
                        ollamaModels.map((m) => (
                          <option key={m.name} value={m.name}>
                            {m.name} ({m.size})
                          </option>
                        ))
                      ) : (
                        <>
                          <option value={draft.selectedModel}>{draft.selectedModel}</option>
                          <option value="" disabled>
                            {ollamaReachable ? "No models installed" : "Ollama not reachable"}
                          </option>
                        </>
                      )}
                    </select>
                  </div>

                  {!ollamaReachable && (
                    <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-[10px]"
                      style={{
                        background: "rgba(239,68,68,0.06)",
                        border: "1px solid rgba(239,68,68,0.12)",
                        color: "#f87171",
                      }}
                    >
                      <XCircle className="w-3 h-3 shrink-0" />
                      <span>Ollama not running at localhost:11434</span>
                    </div>
                  )}
                  {ollamaReachable && ollamaModels.length > 0 && (
                    <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-[10px]"
                      style={{
                        background: "rgba(16,185,129,0.06)",
                        border: "1px solid rgba(16,185,129,0.12)",
                        color: "#34d399",
                      }}
                    >
                      <CheckCircle2 className="w-3 h-3 shrink-0" />
                      <span>{ollamaModels.length} model{ollamaModels.length !== 1 ? "s" : ""} detected</span>
                    </div>
                  )}

                  <button
                    onClick={() => updateDraft({ preferLocal: !draft.preferLocal })}
                    className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg transition-colors"
                    style={{
                      background: "var(--surface-card-bg)",
                      border: "1px solid var(--surface-card-border)",
                    }}
                  >
                    <div className="flex items-center gap-2">
                      {draft.preferLocal ? (
                        <Cpu className="w-3.5 h-3.5" style={{ color: "#34d399" }} />
                      ) : (
                        <Cloud className="w-3.5 h-3.5" style={{ color: "#60a5fa" }} />
                      )}
                      <span className="text-[11px]" style={{ color: "var(--text-secondary)" }}>
                        {draft.preferLocal
                          ? "Prefer local (Ollama first)"
                          : "Prefer API (Groq first)"}
                      </span>
                    </div>
                    {draft.preferLocal ? (
                      <ToggleRight className="w-5 h-5" style={{ color: "#34d399" }} />
                    ) : (
                      <ToggleLeft className="w-5 h-5" style={{ color: "var(--text-muted)" }} />
                    )}
                  </button>
                </div>
              </div>

              <div
                className="px-5 py-4"
                style={{ borderBottom: "1px solid var(--surface-section-border)" }}
              >
                <h3
                  className="text-[11px] font-semibold uppercase tracking-wider mb-3"
                  style={{ color: "var(--text-tertiary)" }}
                >
                  Cache Management
                </h3>

                <div className="flex items-center gap-4 mb-3">
                  <div
                    className="flex items-center gap-2 px-3 py-2 rounded-lg flex-1"
                    style={{
                      background: "var(--surface-card-bg)",
                      border: "1px solid var(--surface-card-border)",
                    }}
                  >
                    <Database className="w-3 h-3" style={{ color: "var(--accent-cyan)" }} />
                    <div>
                      <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>Entries</p>
                      <p className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
                        {settings?.cache_entries ?? 0}
                      </p>
                    </div>
                  </div>
                  <div
                    className="flex items-center gap-2 px-3 py-2 rounded-lg flex-1"
                    style={{
                      background: "var(--surface-card-bg)",
                      border: "1px solid var(--surface-card-border)",
                    }}
                  >
                    <HardDrive className="w-3 h-3" style={{ color: "var(--accent-gold)" }} />
                    <div>
                      <p className="text-[10px]" style={{ color: "var(--text-muted)" }}>Disk Size</p>
                      <p className="text-xs font-semibold" style={{ color: "var(--text-primary)" }}>
                        {settings?.cache_size_mb ?? 0} MB
                      </p>
                    </div>
                  </div>
                </div>

                <button
                  onClick={handleClearCache}
                  disabled={isClearingCache || (settings?.cache_entries ?? 0) === 0}
                  className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg text-[11px] font-medium
                    bg-red-500/8 text-red-400 border border-red-500/15
                    hover:bg-red-500/12 disabled:opacity-30 transition-all"
                >
                  {isClearingCache ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : cacheCleared ? (
                    <Check className="w-3.5 h-3.5" />
                  ) : (
                    <Trash2 className="w-3.5 h-3.5" />
                  )}
                  {cacheCleared ? "Cache Cleared" : "Clear All Cache"}
                </button>
              </div>

              <div
                className="px-5 py-4"
                style={{ borderTop: "1px solid var(--surface-section-border)" }}
              >
                <p className="text-[10px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
                  <span className="font-medium" style={{ color: "var(--text-tertiary)" }}>
                    Fallback chain:
                  </span>{" "}
                  Cache → {draft.preferLocal ? "Ollama → " : ""}Groq → Gemini →
                  Mistral → HuggingFace{!draft.preferLocal ? " → Ollama" : ""}
                </p>
              </div>
            </div>

            {/* Apply / Cancel Footer */}
            <div
              className="flex items-center gap-2 px-5 py-3 shrink-0"
              style={{
                borderTop: "1px solid var(--surface-section-border)",
                background: "var(--settings-bg)",
              }}
            >
              <button
                onClick={handleApply}
                disabled={!isDirty || isApplying}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-[11px] font-semibold transition-all disabled:opacity-30"
                style={{
                  background: isDirty ? "var(--accent-purple)" : "var(--surface-card-bg)",
                  color: isDirty ? "#fff" : "var(--text-muted)",
                  border: isDirty ? "1px solid var(--accent-purple)" : "1px solid var(--surface-card-border)",
                }}
              >
                {isApplying ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Check className="w-3.5 h-3.5" />
                )}
                Apply Settings
              </button>
              <button
                onClick={handleCancel}
                disabled={!isDirty || isApplying}
                className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-[11px] font-medium transition-all disabled:opacity-30"
                style={{
                  background: "var(--surface-card-bg)",
                  color: "var(--text-tertiary)",
                  border: "1px solid var(--surface-card-border)",
                }}
              >
                <X className="w-3.5 h-3.5" />
                Cancel
              </button>

              {applyError && (
                <span className="text-[10px] ml-1" style={{ color: "#f87171" }}>
                  {applyError}
                </span>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
