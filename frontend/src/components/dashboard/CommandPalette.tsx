




import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  Command as CommandIcon,
  FileCode2,
  Code2,
  RotateCcw,
  Settings,
  Box,
  Flame,
  Maximize2,
  Ghost,
  Shield,
  GitFork,
  Brain,
  GraduationCap,
  MessageCircle,
  FileText,
  ShieldAlert,
  GitPullRequest,
  Wrench,
  Clock,
  LayoutGrid,
  CornerDownLeft,
  ArrowUp,
  ArrowDown,
} from "lucide-react";
import {
  getCommands,
  buildDynamicCommands,
  CATEGORY_META,
  type Command,
  type CommandContext,
} from "../../commands/registry";
import { searchIndex } from "../../commands/searchIndex";
import { useAppStore } from "../../store/appStore";
import { getFileContent, explainFile } from "../../api/api";



const ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  FileCode2,
  Code2,
  RotateCcw,
  Settings,
  Box,
  Flame,
  Maximize2,
  Ghost,
  Shield,
  GitFork,
  Brain,
  GraduationCap,
  MessageCircle,
  FileText,
  ShieldAlert,
  GitPullRequest,
  Wrench,
  Clock,
  LayoutGrid,
};

function getIcon(name: string) {
  return ICON_MAP[name] || FileCode2;
}



export function CommandPalette() {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const store = useAppStore();

  
  const allCommands = useMemo(() => {
    if (!isOpen) return [];
    const statics = getCommands();
    const dynamics = buildDynamicCommands(store);
    return [...statics, ...dynamics];
  }, [isOpen, store.graphData, store.parsedFiles]);

  useEffect(() => {
    if (isOpen && allCommands.length > 0) {
      searchIndex.build(allCommands);
    }
  }, [isOpen, allCommands]);

  
  const results = useMemo(() => {
    if (!isOpen) return [];
    return searchIndex.search(query, 25);
  }, [isOpen, query, allCommands]);

  
  useEffect(() => {
    setActiveIndex(0);
  }, [results]);

  
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        e.stopPropagation();
        setIsOpen((prev) => !prev);
      }
      if (e.key === "Escape" && isOpen) {
        e.preventDefault();
        setIsOpen(false);
      }
    };

    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [isOpen]);

  
  useEffect(() => {
    if (isOpen) {
      setQuery("");
      setActiveIndex(0);
      
      requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
    }
  }, [isOpen]);

  
  useEffect(() => {
    const item = itemRefs.current[activeIndex];
    if (item && listRef.current) {
      const container = listRef.current;
      const itemRect = item.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();

      if (itemRect.bottom > containerRect.bottom) {
        item.scrollIntoView({ block: "nearest", behavior: "smooth" });
      } else if (itemRect.top < containerRect.top) {
        item.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    }
  }, [activeIndex]);

  
  const executeCommand = useCallback(
    (cmd: Command) => {
      const ctx: CommandContext = {
        store: useAppStore.getState(),
        selectFile: async (path: string) => {
          const s = useAppStore.getState();
          s.setSelectedFile(path);
          if (s.sessionId) {
            try {
              const content = await getFileContent(s.sessionId, path);
              s.setFileContent(content);
            } catch {  }
            try {
              s.setAILoading(true);
              const ai = await explainFile(s.sessionId, path);
              s.setAIExplanation(ai.explanation, ai.source);
            } catch {  }
            finally { s.setAILoading(false); }
          }
        },
        focusNode: (nodeId: string) => {
          useAppStore.getState().setSelectedFile(nodeId);
          
          window.dispatchEvent(
            new CustomEvent("cmd:focus-node", { detail: nodeId })
          );
        },
      };
      cmd.execute(ctx);
      setIsOpen(false);
    },
    []
  );

  
  const onInputKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((prev) => Math.min(prev + 1, results.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (results[activeIndex]) {
          executeCommand(results[activeIndex]);
        }
      }
    },
    [results, activeIndex, executeCommand]
  );

  
  const grouped = useMemo(() => {
    const groups: { category: string; items: Command[] }[] = [];
    const seen = new Set<string>();

    for (const cmd of results) {
      if (!seen.has(cmd.category)) {
        seen.add(cmd.category);
        groups.push({ category: cmd.category, items: [] });
      }
      groups.find((g) => g.category === cmd.category)!.items.push(cmd);
    }

    return groups;
  }, [results]);

  
  let flatIndex = -1;

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {}
          <motion.div
            className="cmd-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={() => setIsOpen(false)}
          />

          {}
          <motion.div
            className="cmd-palette"
            initial={{ opacity: 0, scale: 0.96, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -20 }}
            transition={{
              duration: 0.2,
              ease: [0.22, 0.61, 0.36, 1],
            }}
          >
            {}
            <div className="cmd-input-wrap">
              <Search className="cmd-input-icon" />
              <input
                ref={inputRef}
                className="cmd-input"
                placeholder="Type a command or search..."
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={onInputKeyDown}
                spellCheck={false}
                autoComplete="off"
              />
              <kbd className="cmd-kbd">ESC</kbd>
            </div>

            {}
            <div className="cmd-divider" />

            {}
            <div className="cmd-results" ref={listRef}>
              {results.length === 0 ? (
                <div className="cmd-empty">
                  <Search className="w-5 h-5 text-slate-700 mb-2" />
                  <span>No results found</span>
                </div>
              ) : (
                grouped.map((group) => {
                  const meta = CATEGORY_META[group.category as keyof typeof CATEGORY_META];
                  return (
                    <div key={group.category} className="cmd-group">
                      <div className="cmd-group-label">
                        <span
                          className="cmd-group-dot"
                          style={{ backgroundColor: meta?.color || "#64748b" }}
                        />
                        {meta?.label || group.category}
                      </div>
                      {group.items.map((cmd) => {
                        flatIndex++;
                        const idx = flatIndex;
                        const isActive = idx === activeIndex;
                        const Icon = getIcon(cmd.icon);

                        return (
                          <button
                            key={cmd.id}
                            ref={(el) => {
                              itemRefs.current[idx] = el;
                            }}
                            className={`cmd-item ${isActive ? "cmd-item-active" : ""}`}
                            onClick={() => executeCommand(cmd)}
                            onMouseEnter={() => setActiveIndex(idx)}
                          >
                            <div className="cmd-item-icon">
                              <Icon className="w-3.5 h-3.5" />
                            </div>
                            <div className="cmd-item-text">
                              <span className="cmd-item-label">
                                {highlightMatch(cmd.label, query)}
                              </span>
                              <span className="cmd-item-desc">{cmd.description}</span>
                            </div>
                            {cmd.shortcut && (
                              <kbd className="cmd-item-shortcut">{cmd.shortcut}</kbd>
                            )}
                            {isActive && (
                              <CornerDownLeft className="cmd-item-enter" />
                            )}
                          </button>
                        );
                      })}
                    </div>
                  );
                })
              )}
            </div>

            {}
            <div className="cmd-footer">
              <div className="cmd-footer-hint">
                <ArrowUp className="w-3 h-3" />
                <ArrowDown className="w-3 h-3" />
                <span>navigate</span>
              </div>
              <div className="cmd-footer-hint">
                <CornerDownLeft className="w-3 h-3" />
                <span>select</span>
              </div>
              <div className="cmd-footer-hint">
                <CommandIcon className="w-3 h-3" />
                <span>K to toggle</span>
              </div>
              <div className="cmd-footer-count">
                {results.length} result{results.length !== 1 ? "s" : ""}
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}



function highlightMatch(text: string, query: string): React.ReactNode {
  if (!query.trim()) return text;

  const q = query.toLowerCase();
  const lower = text.toLowerCase();
  const idx = lower.indexOf(q);

  if (idx === -1) return text;

  return (
    <>
      {text.slice(0, idx)}
      <span className="cmd-highlight">{text.slice(idx, idx + q.length)}</span>
      {text.slice(idx + q.length)}
    </>
  );
}
