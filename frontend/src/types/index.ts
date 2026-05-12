import type { Node, Edge } from "reactflow";

export type AIProvider =
  | "ollama"
  | "groq"
  | "gemini"
  | "mistral"
  | "huggingface";

export interface AIResponse {
  content: string;
  provider: AIProvider;
  tokensUsed: number;
  durationMs: number;
}

export type SessionStatus =
  | "queued"
  | "cloning"
  | "parsing"
  | "done"
  | "error";

export interface AnalysisSession {
  id: string;
  repoUrl: string;
  status: SessionStatus;
  progress: number;
  totalFiles: number;
  parsedFiles: number;
  createdAt: string;
}

export type SymbolKind = "function" | "class" | "constant" | "variable";

export interface CodeSymbol {
  name: string;
  type: SymbolKind;
  lineStart: number;
  lineEnd: number;
  isExported: boolean;
}

export interface FileData {
  path: string;
  language: string;
  content: string;
  lineCount: number;
  complexity: number;
  symbols: CodeSymbol[];
  imports: string[];
  dependents: string[];
}

export interface AppNodeData {
  filePath: string;
  language: string | null;
  complexity: number;
  lineCount: number;
  symbols: string[];
  isCluster: boolean;
  fileCount?: number | undefined;
}

export type AppNode = Node<AppNodeData>;

export interface AppEdgeData {
  edgeType: "import" | "export" | "call";
}

export type AppEdge = Edge<AppEdgeData>;

export interface FileEntry {
  path: string;
  name: string;
  extension: string;
  size_bytes: number;
  language: string | null;
}

export interface IngestResponse {
  session_id: string;
  repo_name: string;
  total_files: number;
  files: FileEntry[];
  ingested_at: string;
  source_type: "github" | "zip";
}

export type IngestTab = "github" | "upload";

export interface ParsedFile {
  path: string;
  language: string | null;
  imports: string[];
  functions: string[];
  classes: string[];
  loc: number;
  nesting_depth: number;
  size_bytes: number;
  complexity_score: number;
}

export interface GraphNode {
  id: string;
  label: string;
  language: string | null;
  loc: number;
  size_bytes: number;
  complexity_score: number;
  imports_count: number;
  functions_count: number;
  classes_count: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface AnalyzeResponse {
  session_id: string;
  repo_name: string;
  total_files: number;
  parsed_files: ParsedFile[];
  graph: GraphData;
}

export interface FileContentResponse {
  path: string;
  content: string;
  language: string | null;
  loc: number;
  size_bytes: number;
}

export interface AIExplainResponse {
  file_path: string;
  explanation: string;
  source: string;
}

export interface AIAnalyzeCodeResponse {
  analysis: string;
  source: string;
}

export interface TopFileEntry {
  path: string;
  complexity_score: number;
}

export interface BeginnerGuideResponse {
  guide: string;
  top_files: TopFileEntry[];
  source: string;
}

export interface FileReference {
  path: string;
  relevance_reason: string;
}

export interface QAResponse {
  answer: string;
  referenced_files: FileReference[];
  source: string;
}

export interface QAHistoryEntry {
  question: string;
  answer: string;
  referenced_files: FileReference[];
  source: string;
  timestamp: number;
}

export interface TreeNode {
  name: string;
  path: string;
  isDir: boolean;
  children: TreeNode[];
  language?: string | null | undefined;
  size_bytes?: number | undefined;
  complexity_score?: number | undefined;
}

export interface ProviderInfo {
  name: string;
  enabled: boolean;
  key_required: boolean;
  key_set: boolean;
  key_masked: string;
  status: string;
  model: string;
  requests_today: number;
  avg_latency_ms: number;
}

export interface SettingsResponse {
  providers: ProviderInfo[];
  active_model: string;
  prefer_local: boolean;
  cache_entries: number;
  cache_size_mb: number;
}

export interface AIStatusResponse {
  ollama: boolean;
  groq: boolean;
  gemini: boolean;
  mistral: boolean;
  huggingface: boolean;
  active_provider: string;
  cache_size: number;
}

export interface KeyUpdateResponse {
  valid: boolean;
  latency_ms: number;
  error: string | null;
}

export interface TestProviderResponse {
  available: boolean;
  latency_ms: number;
  model: string | null;
  error: string | null;
}

export interface ClearCacheResponse {
  cleared_entries: number;
  message: string;
}

export interface DeadFileEntry {
  path: string;
  reason: string;
}

export interface DeadFunctionEntry {
  path: string;
  name: string;
  reason: string;
}

export interface DeadExportEntry {
  path: string;
  symbol: string;
}

export interface DeadCodeSummary {
  total_files: number;
  dead_files_count: number;
  dead_functions_count: number;
  dead_exports_count: number;
  health_score: number;
}

export interface DeadCodeResponse {
  dead_files: DeadFileEntry[];
  dead_functions: DeadFunctionEntry[];
  dead_exports: DeadExportEntry[];
  summary: DeadCodeSummary;
}

export interface FunctionNode {
  id: string;
  name: string;
  start_line: number;
  end_line: number;
  line_count: number;
  complexity: number;
  is_exported: boolean;
}

export interface FunctionEdge {
  id: string;
  source_fn: string;
  target_fn: string;
  call_count: number;
  is_cross_file: boolean;
}

export interface FunctionGraphResponse {
  file_path: string;
  nodes: FunctionNode[];
  edges: FunctionEdge[];
}

export interface ReadmeResponse {
  readme: string;
  source: string;
}

export interface RefactorResponse {
  file_path: string;
  suggestions: string;
  source: string;
}

export interface SecurityFinding {
  file: string;
  line: number;
  severity: "critical" | "high" | "medium" | "low";
  category: "secret" | "injection" | "auth" | "crypto" | "config";
  title: string;
  detail: string;
  fix: string;
}

export interface SecuritySummary {
  files_scanned: number;
  files_with_issues: number;
  total_findings: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  security_score: number;
}

export interface SecurityRecommendation {
  priority: string;
  title: string;
  description: string;
  steps: string[];
}

export interface SecurityScanResponse {
  findings: SecurityFinding[];
  summary: SecuritySummary;
  recommendations: SecurityRecommendation[];
}

export interface PRReviewResponse {
  review: string;
  source: string;
}

export interface FileChange {
  path: string;
  status: string;
  additions: number;
  deletions: number;
}

export interface CommitEntry {
  hash: string;
  short_hash: string;
  timestamp: string;
  author: string;
  message: string;
  files_changed: { path: string; status: string }[];
}

export interface TimelineResponse {
  commits: CommitEntry[];
  total_commits: number;
}

export interface CommitDiffResponse {
  hash: string;
  short_hash: string;
  message: string;
  author: string;
  timestamp: string;
  files: FileChange[];
}

export interface CoverageResponse {
  coverage: Record<string, number>;
  has_coverage: boolean;
  files_covered: number;
  avg_coverage: number;
}

export interface Comment {
  id: string;
  session_id: string;
  target_type: "node" | "file" | "function";
  target_id: string;
  message: string;
  author: string;
  parent_id: string | null;
  created_at: string;
  resolved: boolean;
}

export interface CommentCountsResponse {
  counts: Record<string, number>;
}

export interface ShareTokenResponse {
  token: string;
  session_id: string;
  share_url: string;
}
