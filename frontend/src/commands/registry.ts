export type CommandCategory =
  | "navigation"
  | "graph"
  | "ai"
  | "analysis"
  | "view"
  | "settings"
  | "git";

export interface Command {
  id: string;
  category: CommandCategory;
  label: string;
  description: string;
  keywords: string[];
  icon: string;
  shortcut?: string;
  execute: (ctx: CommandContext) => void;
}

export interface CommandContext {
  store: any;
  selectFile: (path: string) => void;
  focusNode: (nodeId: string) => void;
}

const STATIC_COMMANDS: Command[] = [

  {
    id: "nav:new-session",
    category: "navigation",
    label: "New Session",
    description: "Reset and start a new ingestion",
    keywords: ["new", "reset", "start", "fresh", "session", "ingest"],
    icon: "RotateCcw",
    execute: (ctx) => ctx.store.reset(),
  },
  {
    id: "nav:open-settings",
    category: "settings",
    label: "Open Settings",
    description: "Open the settings panel",
    keywords: ["settings", "config", "preferences", "keys", "api"],
    icon: "Settings",
    shortcut: "⌘,",
    execute: (ctx) => ctx.store.setSettingsPanelOpen(true),
  },

  {
    id: "view:toggle-3d",
    category: "view",
    label: "Toggle 2D / 3D Graph",
    description: "Switch between 2D and 3D graph views",
    keywords: ["3d", "2d", "three", "graph", "toggle", "switch", "view", "perspective"],
    icon: "Box",
    execute: (ctx) => ctx.store.toggle3DGraph(),
  },
  {
    id: "view:toggle-heatmap",
    category: "graph",
    label: "Toggle Heatmap",
    description: "Show complexity heatmap on graph nodes",
    keywords: ["heatmap", "complexity", "heat", "color", "warm"],
    icon: "Flame",
    execute: () => {

      window.dispatchEvent(new CustomEvent("cmd:toggle-heatmap"));
    },
  },
  {
    id: "view:fit-graph",
    category: "graph",
    label: "Fit Graph to View",
    description: "Auto-zoom the graph to fit all nodes",
    keywords: ["fit", "zoom", "center", "view", "reset", "auto"],
    icon: "Maximize2",
    execute: () => {
      window.dispatchEvent(new CustomEvent("cmd:fit-view"));
    },
  },

  {
    id: "analysis:toggle-dead-code",
    category: "analysis",
    label: "Toggle Dead Code",
    description: "Show or hide dead code in the graph",
    keywords: ["dead", "code", "unused", "ghost", "cleanup"],
    icon: "Ghost",
    execute: () => {
      window.dispatchEvent(new CustomEvent("cmd:toggle-dead-code"));
    },
  },
  {
    id: "analysis:toggle-coverage",
    category: "analysis",
    label: "Toggle Coverage Overlay",
    description: "Show test coverage percentages on nodes",
    keywords: ["coverage", "test", "tests", "testing", "percent"],
    icon: "Shield",
    execute: (ctx) => ctx.store.toggleCoverage(),
  },
  {
    id: "analysis:function-graph",
    category: "analysis",
    label: "Open Function Graph",
    description: "Show function-level call graph for selected file",
    keywords: ["function", "call", "graph", "methods", "fn"],
    icon: "GitFork",
    execute: (ctx) => {
      if (ctx.store.selectedFile) {
        ctx.store.toggleFunctionGraph();
      }
    },
  },

  {
    id: "ai:show-insights",
    category: "ai",
    label: "Show AI Insights",
    description: "View AI explanation for the selected file",
    keywords: ["ai", "explain", "insight", "intelligence", "analysis"],
    icon: "Brain",
    execute: () => {

      window.dispatchEvent(new CustomEvent("cmd:show-ai-tab", { detail: "explain" }));
    },
  },
  {
    id: "ai:beginner-guide",
    category: "ai",
    label: "Beginner Guide",
    description: "Generate a beginner-friendly codebase walkthrough",
    keywords: ["beginner", "guide", "onboard", "walkthrough", "learn"],
    icon: "GraduationCap",
    execute: () => {
      window.dispatchEvent(new CustomEvent("cmd:show-ai-tab", { detail: "beginner" }));
    },
  },
  {
    id: "ai:ask-question",
    category: "ai",
    label: "Ask AI a Question",
    description: "Open the Q&A panel to ask about the codebase",
    keywords: ["ask", "question", "qa", "chat", "query"],
    icon: "MessageCircle",
    execute: () => {
      window.dispatchEvent(new CustomEvent("cmd:show-ai-tab", { detail: "qa" }));
    },
  },
  {
    id: "ai:generate-readme",
    category: "ai",
    label: "Generate README",
    description: "Auto-generate a README for the project",
    keywords: ["readme", "documentation", "docs", "generate", "markdown"],
    icon: "FileText",
    execute: () => {
      window.dispatchEvent(new CustomEvent("cmd:show-advanced-ai", { detail: "readme" }));
    },
  },
  {
    id: "ai:security-scan",
    category: "ai",
    label: "Run Security Scan",
    description: "Scan the codebase for security vulnerabilities",
    keywords: ["security", "scan", "vulnerability", "audit", "safe"],
    icon: "ShieldAlert",
    execute: () => {
      window.dispatchEvent(new CustomEvent("cmd:show-advanced-ai", { detail: "security" }));
    },
  },
  {
    id: "ai:pr-review",
    category: "ai",
    label: "Generate PR Review",
    description: "Create a pull request review summary",
    keywords: ["pr", "pull", "request", "review", "code review"],
    icon: "GitPullRequest",
    execute: () => {
      window.dispatchEvent(new CustomEvent("cmd:show-advanced-ai", { detail: "pr" }));
    },
  },
  {
    id: "ai:refactor",
    category: "ai",
    label: "Refactor Suggestions",
    description: "Get AI refactoring suggestions for selected file",
    keywords: ["refactor", "improve", "clean", "suggestions", "optimize"],
    icon: "Wrench",
    execute: () => {
      window.dispatchEvent(new CustomEvent("cmd:show-advanced-ai", { detail: "refactor" }));
    },
  },

  {
    id: "git:timeline",
    category: "git",
    label: "Open Git Timeline",
    description: "View commit history timeline",
    keywords: ["git", "timeline", "history", "commits", "log"],
    icon: "Clock",
    execute: () => {
      window.dispatchEvent(new CustomEvent("cmd:show-git-timeline"));
    },
  },

  {
    id: "graph:layout-force",
    category: "graph",
    label: "Layout: Force-Directed",
    description: "Switch graph to force-directed layout",
    keywords: ["layout", "force", "directed", "organic"],
    icon: "LayoutGrid",
    execute: () => {
      window.dispatchEvent(new CustomEvent("cmd:change-layout", { detail: "force" }));
    },
  },
  {
    id: "graph:layout-hierarchical",
    category: "graph",
    label: "Layout: Hierarchical",
    description: "Switch graph to hierarchical layout",
    keywords: ["layout", "hierarchical", "tree", "top-down"],
    icon: "LayoutGrid",
    execute: () => {
      window.dispatchEvent(new CustomEvent("cmd:change-layout", { detail: "hierarchical" }));
    },
  },
  {
    id: "graph:layout-radial",
    category: "graph",
    label: "Layout: Radial",
    description: "Switch graph to radial layout",
    keywords: ["layout", "radial", "circular", "orbit"],
    icon: "LayoutGrid",
    execute: () => {
      window.dispatchEvent(new CustomEvent("cmd:change-layout", { detail: "radial" }));
    },
  },
  {
    id: "graph:layout-layered",
    category: "graph",
    label: "Layout: Layered",
    description: "Switch graph to language-layered layout",
    keywords: ["layout", "layered", "language", "grouped"],
    icon: "LayoutGrid",
    execute: () => {
      window.dispatchEvent(new CustomEvent("cmd:change-layout", { detail: "layered" }));
    },
  },
];

export const CATEGORY_META: Record<CommandCategory, { label: string; color: string }> = {
  navigation: { label: "Navigation", color: "#f6c445" },
  graph: { label: "Graph", color: "#7c6ee0" },
  ai: { label: "AI", color: "#22d3ee" },
  analysis: { label: "Analysis", color: "#8b5cf6" },
  view: { label: "View", color: "#3b82f6" },
  settings: { label: "Settings", color: "#94a3b8" },
  git: { label: "Git", color: "#10b981" },
};

let _commands: Command[] = [...STATIC_COMMANDS];

export function getCommands(): Command[] {
  return _commands;
}

export function registerCommand(cmd: Command): void {
  _commands.push(cmd);
}

export function unregisterCommand(id: string): void {
  _commands = _commands.filter((c) => c.id !== id);
}

export function buildDynamicCommands(store: any): Command[] {
  const dynamic: Command[] = [];

  if (store.graphData?.nodes) {
    for (const node of store.graphData.nodes) {
      dynamic.push({
        id: `file:${node.id}`,
        category: "navigation",
        label: `Go to ${node.label}`,
        description: `${node.language || "Unknown"} · ${node.loc} LOC`,
        keywords: [
          node.label.toLowerCase(),
          node.id.toLowerCase(),
          node.language?.toLowerCase() || "",
          "file",
          "go",
          "open",
          "navigate",
        ],
        icon: "FileCode2",
        execute: (ctx) => ctx.selectFile(node.id),
      });
    }
  }

  if (store.parsedFiles) {
    for (const pf of store.parsedFiles) {
      for (const fn of pf.functions) {
        dynamic.push({
          id: `fn:${pf.path}:${fn}`,
          category: "navigation",
          label: `Function: ${fn}`,
          description: `in ${pf.path.split("/").pop()}`,
          keywords: [fn.toLowerCase(), "function", "method", "def"],
          icon: "Code2",
          execute: (ctx) => ctx.selectFile(pf.path),
        });
      }
    }
  }

  return dynamic;
}
