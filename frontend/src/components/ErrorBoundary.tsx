import React from "react";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  onReset?: () => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error("[ErrorBoundary] Caught error:", error, info.componentStack);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
    this.props.onReset?.();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "0.75rem",
            padding: "2rem",
            textAlign: "center",
            height: "100%",
          }}
        >
          <p
            style={{
              fontSize: "12px",
              color: "var(--text-secondary, #94a3b8)",
            }}
          >
            Something went wrong rendering this view.
          </p>
          {this.state.error && (
            <p
              style={{
                fontSize: "10px",
                color: "var(--text-muted, #64748b)",
                fontFamily: "monospace",
                maxWidth: "320px",
                wordBreak: "break-word",
              }}
            >
              {this.state.error.message}
            </p>
          )}
          <button
            onClick={this.handleReset}
            style={{
              padding: "6px 14px",
              borderRadius: "8px",
              fontSize: "11px",
              fontWeight: 600,
              cursor: "pointer",
              color: "var(--text-secondary, #94a3b8)",
              background: "var(--bg-input, rgba(255,255,255,0.05))",
              border: "1px solid var(--border-light, rgba(255,255,255,0.1))",
              transition: "opacity 0.15s",
            }}
          >
            Close and return
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
