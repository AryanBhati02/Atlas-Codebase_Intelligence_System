




import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronRight,
  Folder,
  FolderOpen,
  FileCode2,
  Search,
  X,
} from "lucide-react";
import { useAppStore } from "../../store/appStore";
import { getFileContent } from "../../api/api";
import type { TreeNode, ParsedFile } from "../../types";


function buildTree(files: ParsedFile[]): TreeNode[] {
  const root: TreeNode[] = [];

  for (const f of files) {
    const parts = f.path.split("/");
    let current = root;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isFile = i === parts.length - 1;
      const existing = current.find((n) => n.name === part);

      if (existing) {
        current = existing.children;
      } else {
        const node: TreeNode = {
          name: part,
          path: isFile ? f.path : parts.slice(0, i + 1).join("/"),
          isDir: !isFile,
          children: [],
          language: isFile ? f.language : null,
          size_bytes: isFile ? f.size_bytes : 0,
          complexity_score: isFile ? f.complexity_score : 0,
        };
        current.push(node);
        current = node.children;
      }
    }
  }

  const sortTree = (nodes: TreeNode[]): TreeNode[] => {
    nodes.sort((a, b) => {
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    nodes.forEach((n) => sortTree(n.children));
    return nodes;
  };

  return sortTree(root);
}

function getComplexityColor(score: number): string {
  if (score >= 0.7) return "#ef4444";
  if (score >= 0.4) return "#f59e0b";
  return "#22d3ee";
}

function getFileIcon(lang: string | null): string {
  const colors: Record<string, string> = {
    Python: "#3b82f6",
    JavaScript: "#f59e0b",
    TypeScript: "#38bdf8",
    JSON: "#10b981",
    HTML: "#f43f5e",
    CSS: "#8b5cf6",
  };
  return lang ? colors[lang] || "#64748b" : "#64748b";
}

export function FileExplorer() {
  const {
    parsedFiles,
    selectedFile,
    sessionId,
    setSelectedFile,
    setFileContent,
  } = useAppStore();
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const tree = useMemo(() => buildTree(parsedFiles), [parsedFiles]);

  const filteredTree = useMemo(() => {
    if (!search.trim()) return tree;
    const q = search.toLowerCase();

    const filterNodes = (nodes: TreeNode[]): TreeNode[] => {
      const result: TreeNode[] = [];
      for (const node of nodes) {
        if (node.isDir) {
          const children = filterNodes(node.children);
          if (children.length > 0) result.push({ ...node, children });
        } else if (
          node.name.toLowerCase().includes(q) ||
          node.path.toLowerCase().includes(q)
        ) {
          result.push(node);
        }
      }
      return result;
    };

    return filterNodes(tree);
  }, [tree, search]);

  const toggleExpand = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const handleFileClick = async (path: string) => {
    if (!sessionId) return;
    setSelectedFile(path);
    try {
      const content = await getFileContent(sessionId, path);
      setFileContent(content);
    } catch { /* no-op */ }
    // ExplainTab auto-streams the explanation when selectedFile changes
  };

  const renderNode = (node: TreeNode, depth: number) => {
    const isOpen = expanded.has(node.path);
    const isActive = selectedFile === node.path;

    if (node.isDir) {
      return (
        <div key={node.path}>
          <motion.div
            className="tree-item"
            style={{ paddingLeft: 10 + depth * 16 }}
            onClick={() => toggleExpand(node.path)}
            whileTap={{ scale: 0.98 }}
          >
            <motion.div
              animate={{ rotate: isOpen ? 90 : 0 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
            >
              <ChevronRight className="w-3 h-3 shrink-0" style={{ color: "var(--text-muted)" }} />
            </motion.div>
            {isOpen ? (
              <FolderOpen className="w-3.5 h-3.5 text-accent-gold/70 shrink-0" />
            ) : (
              <Folder className="w-3.5 h-3.5 shrink-0" style={{ color: "var(--text-muted)" }} />
            )}
            <span className="truncate text-[11.5px]">{node.name}</span>
            <span className="text-[9px] ml-auto tabular-nums" style={{ color: "var(--text-muted)" }}>
              {node.children.length}
            </span>
          </motion.div>

          <AnimatePresence>
            {isOpen && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.2, ease: [0.25, 0.46, 0.45, 0.94] }}
                style={{ overflow: "hidden" }}
              >
                {node.children.map((child) => renderNode(child, depth + 1))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      );
    }

    return (
      <motion.div
        key={node.path}
        className={`tree-item ${isActive ? "active" : ""}`}
        style={{ paddingLeft: 10 + depth * 16 }}
        onClick={() => handleFileClick(node.path)}
        whileTap={{ scale: 0.98 }}
        whileHover={{ x: 2 }}
        transition={{ duration: 0.15 }}
      >
        <FileCode2
          className="w-3 h-3 shrink-0"
          style={{ color: isActive ? "#f6c445" : getFileIcon(node.language ?? null) }}
        />
        <span className="truncate flex-1 text-[11.5px]">{node.name}</span>
        {node.complexity_score !== undefined && node.complexity_score > 0 && (
          <div
            className="complexity-dot"
            style={{
              backgroundColor: getComplexityColor(node.complexity_score),
            }}
            title={`Complexity: ${(node.complexity_score * 100).toFixed(0)}%`}
          />
        )}
      </motion.div>
    );
  };

  return (
    <>
      <div className="panel-header">
        <h2>Explorer</h2>
        <span className="text-[9px] font-medium tabular-nums" style={{ color: "var(--text-muted)" }}>
          {parsedFiles.length} files
        </span>
      </div>

      { }
      <div className="px-2.5 py-2" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3" style={{ color: "var(--text-muted)" }} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search files…"
            className="w-full pl-7 pr-7 py-1.5 rounded-lg
              text-[11px] transition-all duration-300"
            style={{
              background: "var(--bg-input)",
              border: "1px solid var(--border-subtle)",
              color: "var(--text-primary)",
            }}
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded transition-colors"
              style={{ color: "var(--text-muted)" }}
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      { }
      <div className="panel-body py-1">
        {filteredTree.map((node) => renderNode(node, 0))}
      </div>
    </>
  );
}
