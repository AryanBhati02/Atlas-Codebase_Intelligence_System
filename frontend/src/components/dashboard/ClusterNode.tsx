import React from "react";
import { Handle, Position, type NodeProps } from "reactflow";
import { FolderOpen, FolderClosed, ChevronRight, ChevronDown } from "lucide-react";
import type { ClusterNodeData } from "../../utils/graphClustering";

const LANG_COLORS: Record<string, string> = {
  Python: "#3b82f6",
  JavaScript: "#f59e0b",
  TypeScript: "#38bdf8",
  Java: "#f97316",
  Go: "#06b6d4",
  Rust: "#ef4444",
  "C++": "#ec4899",
  C: "#94a3b8",
  HTML: "#f43f5e",
  CSS: "#8b5cf6",
  JSON: "#10b981",
  Markdown: "#6b7280",
  YAML: "#84cc16",
  Shell: "#22c55e",
  Ruby: "#ef4444",
  PHP: "#818cf8",
};

function complexityColor(c: number): string {
  if (c < 0.3) return "#22c55e";
  if (c < 0.5) return "#84cc16";
  if (c < 0.7) return "#f59e0b";
  return "#ef4444";
}

export const ClusterNodeComponent = React.memo(function ClusterNodeComponent({
  id,
  data,
}: NodeProps<ClusterNodeData>) {
  const color = complexityColor(data.avgComplexity);

  const langCounts = new Map<string, number>();
  for (const child of data.children) {
    const lang = child.data.language;
    if (lang) langCounts.set(lang, (langCounts.get(lang) ?? 0) + 1);
  }
  const topLangs = Array.from(langCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  if (data.expanded) {
    return (
      <>
        <Handle
          type="target"
          position={Position.Top}
          style={{ background: "var(--accent-purple)", border: "none", width: 4, height: 4 }}
        />
        <div
          style={{
            width: 200,
            background: "var(--bg-elevated)",
            border: "1.5px dashed var(--accent-purple-border)",
            borderRadius: 8,
            padding: "6px 10px",
            display: "flex",
            alignItems: "center",
            gap: 7,
            backdropFilter: "blur(8px)",
            cursor: "pointer",
          }}
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            window.dispatchEvent(
              new CustomEvent("cluster:toggle", { detail: id })
            );
          }}
        >
          <FolderOpen size={11} style={{ color: "var(--accent-violet)", flexShrink: 0 }} />
          <span
            style={{
              color: "var(--text-secondary)",
              fontSize: 10,
              fontWeight: 600,
              flex: 1,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {data.label}
          </span>
          <span
            style={{
              color: "var(--text-muted)",
              fontSize: 9,
              flexShrink: 0,
            }}
          >
            {data.fileCount} files
          </span>
          <ChevronDown size={10} style={{ color: "var(--accent-purple)", flexShrink: 0 }} />
        </div>
        <Handle
          type="source"
          position={Position.Bottom}
          style={{ background: "var(--accent-purple)", border: "none", width: 4, height: 4 }}
        />
      </>
    );
  }

  return (
    <>
      <Handle
        type="target"
        position={Position.Top}
        style={{ background: "var(--accent-purple)", border: "none", width: 5, height: 5 }}
      />

      <div
        style={{
          width: 280,
          minHeight: 80,
          background: "var(--bg-surface-solid)",
          border: "1.5px dashed var(--accent-purple-border-hover)",
          borderRadius: 12,
          padding: "10px 12px",
          display: "flex",
          flexDirection: "column",
          gap: 7,
          backdropFilter: "blur(14px)",
          boxShadow:
            "0 4px 28px var(--shadow-color), inset 0 1px 0 var(--border-subtle)",
        }}
      >
        {}
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <FolderClosed
            size={13}
            style={{ color: "var(--accent-violet)", flexShrink: 0 }}
          />
          <span
            style={{
              color: "var(--text-primary)",
              fontSize: 12,
              fontWeight: 600,
              flex: 1,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              letterSpacing: "-0.01em",
            }}
          >
            {data.label}
          </span>

          {}
          <span
            style={{
              background: "var(--accent-purple-muted)",
              color: "var(--accent-violet)",
              fontSize: 9,
              fontWeight: 700,
              padding: "2px 7px",
              borderRadius: 99,
              flexShrink: 0,
              letterSpacing: "0.03em",
            }}
          >
            {data.fileCount} files
          </span>

          {}
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              window.dispatchEvent(
                new CustomEvent("cluster:toggle", { detail: id })
              );
            }}
            style={{
              background: "var(--accent-purple-subtle)",
              border: "1px solid var(--accent-purple-border)",
              borderRadius: 6,
              cursor: "pointer",
              padding: "2px 4px",
              color: "var(--accent-violet)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
              lineHeight: 0,
            }}
          >
            <ChevronRight size={10} />
          </button>
        </div>

        {}
        {topLangs.length > 0 && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 4,
              flexWrap: "wrap",
            }}
          >
            {topLangs.map(([lang, count]) => (
              <span
                key={lang}
                title={`${lang}: ${count} files`}
                style={{ display: "flex", alignItems: "center", gap: 3 }}
              >
                <span
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: "50%",
                    background: LANG_COLORS[lang] ?? "#7c6ee0",
                    display: "inline-block",
                    flexShrink: 0,
                    boxShadow: `0 0 4px ${LANG_COLORS[lang] ?? "#7c6ee0"}60`,
                  }}
                />
              </span>
            ))}
            <span
              style={{
                color: "var(--text-tertiary)",
                fontSize: 9,
                marginLeft: 2,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                maxWidth: 170,
              }}
            >
              {topLangs.map(([l]) => l).join(", ")}
            </span>
          </div>
        )}

        {}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span
            style={{
              color: "var(--text-tertiary)",
              fontSize: 8,
              flexShrink: 0,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              fontWeight: 700,
            }}
          >
            complexity
          </span>
          <div
            style={{
              flex: 1,
              height: 3,
              background: "var(--border-medium)",
              borderRadius: 99,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${Math.round(data.avgComplexity * 100)}%`,
                height: "100%",
                background: color,
                borderRadius: 99,
                transition: "width 0.4s ease",
                boxShadow: `0 0 4px ${color}80`,
              }}
            />
          </div>
          <span
            style={{
              color,
              fontSize: 9,
              flexShrink: 0,
              fontWeight: 700,
              minWidth: 24,
              textAlign: "right",
            }}
          >
            {Math.round(data.avgComplexity * 100)}%
          </span>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        style={{ background: "var(--accent-purple)", border: "none", width: 5, height: 5 }}
      />
    </>
  );
});
