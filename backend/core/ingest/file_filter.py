"""
File filtering and language detection for ingested repositories.
Walks a directory tree, skips noise (node_modules, binaries, etc.),
and returns a clean list of source files with metadata.
"""

import os
from pathlib import Path

from config import IGNORED_DIRS, IGNORED_EXTENSIONS, MAX_FILE_SIZE_BYTES
from models.schemas import FileEntry




LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C",
    ".hpp": "C++",
    ".cs": "C#",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".r": "R",
    ".dart": "Dart",
    ".lua": "Lua",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sass": "Sass",
    ".less": "Less",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".xml": "XML",
    ".toml": "TOML",
    ".ini": "INI",
    ".cfg": "Config",
    ".conf": "Config",
    ".md": "Markdown",
    ".rst": "reStructuredText",
    ".txt": "Text",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".astro": "Astro",
    ".dockerfile": "Docker",
    ".tf": "Terraform",
    ".proto": "Protobuf",
    ".graphql": "GraphQL",
    ".gql": "GraphQL",
}


def detect_language(extension: str) -> str | None:
    """Map a file extension to a language name."""
    return LANGUAGE_MAP.get(extension.lower())


def should_ignore_dir(dir_name: str) -> bool:
    """Check if a directory should be skipped during traversal."""
    return dir_name in IGNORED_DIRS or dir_name.startswith(".")


def should_ignore_file(file_path: Path, file_size: int) -> bool:
    """Check if a file should be excluded from results."""
    if file_path.suffix.lower() in IGNORED_EXTENSIONS:
        return True
    if file_size > MAX_FILE_SIZE_BYTES:
        return True
    if file_path.name.startswith("."):
        return True
    return False


def scan_directory_iter(repo_dir: Path):
    """
    Generator: recursively yield FileEntry objects from a directory.
    Memory-efficient — does not build the full list in memory.
    Skips ignored directories and files based on configured rules.
    """
    for root, dirs, files in os.walk(repo_dir):
        
        dirs[:] = sorted(d for d in dirs if not should_ignore_dir(d))

        for filename in sorted(files):
            file_path = Path(root) / filename

            try:
                file_size = file_path.stat().st_size
            except OSError:
                continue

            if should_ignore_file(file_path, file_size):
                continue

            relative_path = file_path.relative_to(repo_dir)
            extension = file_path.suffix
            language = detect_language(extension)

            yield FileEntry(
                path=str(relative_path).replace("\\", "/"),
                name=filename,
                extension=extension,
                size_bytes=file_size,
                language=language,
            )


def scan_directory(repo_dir: Path, max_files: int | None = None) -> list[FileEntry]:
    """
    Recursively scan a directory and return filtered file entries.
    Enforces MAX_FILES_LIMIT to prevent OOM on massive repos.
    Returns a list capped at max_files (default: config MAX_FILES_LIMIT).
    """
    from config import MAX_FILES_LIMIT
    limit = max_files if max_files is not None else MAX_FILES_LIMIT

    entries: list[FileEntry] = []
    for entry in scan_directory_iter(repo_dir):
        entries.append(entry)
        if len(entries) >= limit:
            import logging
            logging.getLogger("codebase-intel.ingest").warning(
                f"File limit reached ({limit}). Truncating scan. "
                f"Repo has more files than the configured MAX_FILES_LIMIT."
            )
            break

    return entries

