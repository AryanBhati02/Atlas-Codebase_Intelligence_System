from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SESSIONS_DIR = BASE_DIR / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

IGNORED_DIRS: set[str] = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", ".next", ".nuxt",
    "coverage", ".nyc_output", ".cache", ".parcel-cache",
    "bower_components", "vendor", ".idea", ".vscode",
    ".gradle", "target", "bin", "obj", ".tox",
    ".eggs", "site-packages", ".svn", ".hg",
}

IGNORED_EXTENSIONS: set[str] = {
    
    ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe",
    ".o", ".a", ".lib", ".obj", ".class", ".jar", ".war",
    
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".svg", ".webp",
    
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flac", ".mkv",
    
    ".zip", ".tar", ".gz", ".bz2", ".rar", ".7z", ".xz",
    
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    
    ".sqlite", ".db", ".mdb",
    
    ".lock",
    
    ".map",
}

MAX_FILE_SIZE_BYTES: int = 500 * 1024  

MAX_FILES_LIMIT: int = 100_000          
ANALYSIS_TIMEOUT_SECONDS: int = 600     
PARSE_BATCH_SIZE: int = 500             

CORS_ORIGINS: list[str] = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

SESSION_LIFETIME_HOURS: int = 4
