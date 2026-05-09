
from pydantic import BaseModel
from typing import Optional

class GitHubIngestRequest(BaseModel):
    url: str

class FileEntry(BaseModel):
    path: str
    name: str
    extension: str
    size_bytes: int
    language: Optional[str] = None

class IngestResponse(BaseModel):
    session_id: str
    repo_name: str
    total_files: int
    files: list[FileEntry]
    ingested_at: str
    source_type: str

class ParsedFile(BaseModel):
    path: str
    language: Optional[str] = None
    imports: list[str] = []
    functions: list[str] = []
    classes: list[str] = []
    loc: int = 0
    nesting_depth: int = 0
    size_bytes: int = 0
    complexity_score: float = 0.0

class GraphNode(BaseModel):
    id: str
    label: str
    language: Optional[str] = None
    loc: int = 0
    size_bytes: int = 0
    complexity_score: float = 0.0
    imports_count: int = 0
    functions_count: int = 0
    classes_count: int = 0

class GraphEdge(BaseModel):
    id: str
    source: str
    target: str

class GraphData(BaseModel):
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

class AnalyzeResponse(BaseModel):
    session_id: str
    repo_name: str
    total_files: int
    parsed_files: list[ParsedFile] = []
    graph: GraphData = GraphData()

class FileContentResponse(BaseModel):
    path: str
    content: str
    language: Optional[str] = None
    loc: int = 0
    size_bytes: int = 0

class AIExplainRequest(BaseModel):
    session_id: str
    file_path: str

class AIExplainResponse(BaseModel):
    file_path: str
    explanation: str
    source: str

class AIAnalyzeCodeRequest(BaseModel):
    session_id: str
    file_path: str
    code: str
    start_line: int = 0
    end_line: int = 0

class AIAnalyzeCodeResponse(BaseModel):
    analysis: str
    source: str

class BeginnerGuideRequest(BaseModel):
    session_id: str

class TopFileEntry(BaseModel):
    path: str
    complexity_score: float = 0.0

class BeginnerGuideResponse(BaseModel):
    guide: str
    top_files: list[TopFileEntry] = []
    source: str

class QARequest(BaseModel):
    session_id: str
    question: str

class FileReference(BaseModel):
    path: str
    relevance_reason: str = ""

class QAResponse(BaseModel):
    answer: str
    referenced_files: list[FileReference] = []
    source: str

class DeadFileEntry(BaseModel):
    path: str
    reason: str

class DeadFunctionEntry(BaseModel):
    path: str
    name: str
    reason: str

class DeadExportEntry(BaseModel):
    path: str
    symbol: str

class DeadCodeSummary(BaseModel):
    total_files: int = 0
    dead_files_count: int = 0
    dead_functions_count: int = 0
    dead_exports_count: int = 0
    health_score: float = 1.0

class DeadCodeResponse(BaseModel):
    dead_files: list[DeadFileEntry] = []
    dead_functions: list[DeadFunctionEntry] = []
    dead_exports: list[DeadExportEntry] = []
    summary: DeadCodeSummary = DeadCodeSummary()

class FunctionNode(BaseModel):
    id: str
    name: str
    start_line: int = 0
    end_line: int = 0
    line_count: int = 0
    complexity: float = 0.0
    is_exported: bool = False

class FunctionEdge(BaseModel):
    id: str
    source_fn: str
    target_fn: str
    call_count: int = 1
    is_cross_file: bool = False

class FunctionGraphResponse(BaseModel):
    file_path: str
    nodes: list[FunctionNode] = []
    edges: list[FunctionEdge] = []

class ReadmeRequest(BaseModel):
    session_id: str

class ReadmeResponse(BaseModel):
    readme: str
    source: str

class RefactorRequest(BaseModel):
    session_id: str
    file_path: str

class RefactorResponse(BaseModel):
    file_path: str
    suggestions: str
    source: str

class SecurityFinding(BaseModel):
    file: str
    line: int = 0
    severity: str = "medium"
    category: str = ""
    title: str = ""
    detail: str = ""
    fix: str = ""

class SecuritySummary(BaseModel):
    files_scanned: int = 0
    files_with_issues: int = 0
    total_findings: int = 0
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    security_score: float = 1.0

class SecurityScanRequest(BaseModel):
    session_id: str

class SecurityRecommendation(BaseModel):
    priority: str = "medium"
    title: str = ""
    description: str = ""
    steps: list[str] = []

class SecurityScanResponse(BaseModel):
    findings: list[SecurityFinding] = []
    summary: SecuritySummary = SecuritySummary()
    recommendations: list[SecurityRecommendation] = []

class PRReviewRequest(BaseModel):
    session_id: str
    file_paths: list[str] = []

class PRReviewResponse(BaseModel):
    review: str
    source: str

class FileChange(BaseModel):
    path: str
    status: str
    additions: int = 0
    deletions: int = 0

class CommitEntry(BaseModel):
    hash: str
    short_hash: str
    timestamp: str
    author: str
    message: str
    files_changed: list[dict] = []

class TimelineResponse(BaseModel):
    commits: list[CommitEntry] = []
    total_commits: int = 0

class CommitDiffResponse(BaseModel):
    hash: str
    short_hash: str = ""
    message: str = ""
    author: str = ""
    timestamp: str = ""
    files: list[FileChange] = []

class CoverageResponse(BaseModel):
    coverage: dict[str, float] = {}
    has_coverage: bool = False
    files_covered: int = 0
    avg_coverage: float = 0

class CommentCreate(BaseModel):
    session_id: str
    target_type: str  
    target_id: str
    message: str
    author: str = "Anonymous"
    parent_id: Optional[str] = None

class CommentResponse(BaseModel):
    id: str
    session_id: str
    target_type: str
    target_id: str
    message: str
    author: str
    parent_id: Optional[str] = None
    created_at: str
    resolved: bool = False

class CommentCountsResponse(BaseModel):
    counts: dict[str, int] = {}

class ShareTokenResponse(BaseModel):
    token: str
    session_id: str
    share_url: str

class ErrorResponse(BaseModel):
    error: str
    error_code: Optional[str] = None
    session_id: Optional[str] = None
    detail: Optional[str] = None

class ProgressResponse(BaseModel):

    progress: float = 0.0
    files_done: int = 0
    total_files: int = 0
    status: str = "pending"
    partial_nodes: list = []
    partial_edges: list = []
    error: Optional[str] = None

    stage: str = "pending"
    current: int = 0
    total: int = 0
    done: bool = False
