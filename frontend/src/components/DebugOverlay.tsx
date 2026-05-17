import React, { useState, useEffect, useRef } from "react";

export interface DebugState {
  backendReachable: boolean | null;
  sessionId: string | null;
  pollingActive: boolean;
  pollCount: number;
  lastStage: string | null;
  lastCurrent: number;
  lastTotal: number;
  lastPollMs: number | null;
  apiBase: string;
}

interface Props {
  state: DebugState;
}

export const DebugOverlay = React.memo(function DebugOverlay({ state }: Props) {
  const [visible, setVisible] = useState(false);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Alt+D to toggle
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.altKey && e.key.toLowerCase() === "d") {
        setVisible((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Update elapsed since last poll
  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (state.lastPollMs !== null) {
      timerRef.current = setInterval(() => {
        setElapsedMs(Date.now() - (state.lastPollMs ?? Date.now()));
      }, 250);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [state.lastPollMs]);

  if (!visible) {
    return (
      <div
        onClick={() => setVisible(true)}
        title="Alt+D — open debug overlay"
        style={{
          position: "fixed",
          bottom: "0.5rem",
          left: "0.5rem",
          zIndex: 99999,
          width: "0.5rem",
          height: "0.5rem",
          borderRadius: "50%",
          background: state.backendReachable === false
            ? "#f87171"
            : state.pollingActive
              ? "#34d399"
              : "#94a3b8",
          cursor: "pointer",
          opacity: 0.5,
        }}
      />
    );
  }

  const row = (label: string, value: React.ReactNode, ok?: boolean) => (
    <div style={{ display: "flex", gap: "0.5rem", alignItems: "baseline" }}>
      <span style={{ color: "#94a3b8", minWidth: "10rem", fontSize: "0.65rem" }}>{label}</span>
      <span style={{
        color: ok === true ? "#34d399" : ok === false ? "#f87171" : "#e2e8f0",
        fontFamily: "monospace",
        fontSize: "0.7rem",
        wordBreak: "break-all",
      }}>
        {value}
      </span>
    </div>
  );

  const reachableColor = state.backendReachable === null ? "#94a3b8"
    : state.backendReachable ? "#34d399" : "#f87171";
  const reachableLabel = state.backendReachable === null ? "checking…"
    : state.backendReachable ? "reachable" : "UNREACHABLE";

  return (
    <div
      style={{
        position: "fixed",
        bottom: "1rem",
        left: "1rem",
        zIndex: 99999,
        padding: "0.75rem 1rem",
        borderRadius: "0.75rem",
        background: "rgba(15,20,30,0.92)",
        border: "1px solid rgba(255,255,255,0.08)",
        backdropFilter: "blur(12px)",
        display: "flex",
        flexDirection: "column",
        gap: "0.35rem",
        minWidth: "22rem",
        maxWidth: "28rem",
        fontFamily: "system-ui, sans-serif",
        userSelect: "none",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.25rem" }}>
        <span style={{ color: "#7c3aed", fontWeight: 700, fontSize: "0.65rem", letterSpacing: "0.1em" }}>
          ATLAS DEBUG (Alt+D)
        </span>
        <button
          onClick={() => setVisible(false)}
          style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", fontSize: "0.8rem", lineHeight: 1, padding: 0 }}
        >
          ×
        </button>
      </div>

      {row(
        "Backend",
        <span style={{ color: reachableColor }}>{reachableLabel}</span>,
        state.backendReachable === null ? undefined : state.backendReachable,
      )}
      {row("API base", state.apiBase)}
      {row("Session ID", state.sessionId ?? "(none)")}
      {row(
        "Polling",
        state.pollingActive ? `active — ${state.pollCount} polls` : "idle",
        state.pollingActive,
      )}
      {state.pollingActive && row(
        "Stage",
        state.lastStage
          ? `${state.lastStage} (${state.lastCurrent}/${state.lastTotal})`
          : "—",
      )}
      {row(
        "Last poll",
        state.lastPollMs
          ? `${Math.round((elapsedMs ?? 0) / 100) / 10}s ago`
          : "—",
      )}

      <div style={{ marginTop: "0.25rem", borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "0.35rem" }}>
        <span style={{ color: "#475569", fontSize: "0.6rem" }}>
          localStorage: atlas-session-v1
          {" · "}
          StrictMode: {import.meta.env.DEV ? "ON (dev)" : "off"}
        </span>
      </div>
    </div>
  );
});
