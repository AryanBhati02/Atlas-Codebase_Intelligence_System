"""Advanced AI Capabilities — README gen, Refactor suggestions, Security scan, PR Review.

Uses parsed file data, graph edges, dead code, and complexity metrics
to produce context-aware, structured insights. Each feature has a rich
template fallback + AI-enhanced path via route_prompt.
"""

import re
import json
from pathlib import Path
from typing import Optional
from core.ai.router import route_prompt




def _build_readme_fallback(repo_name: str, parsed_files: list[dict], graph: dict) -> str:
    """Generate a comprehensive README from codebase metadata."""
    
    lang_counts: dict[str, int] = {}
    total_loc = 0
    for f in parsed_files:
        lang = f.get("language") or "Other"
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
        total_loc += f.get("loc", 0)
    primary_lang = max(lang_counts, key=lang_counts.get) if lang_counts else "Unknown"

    
    dir_map: dict[str, list[str]] = {}
    for f in parsed_files:
        parts = f["path"].split("/")
        folder = parts[0] if len(parts) > 1 else "root"
        if folder not in dir_map:
            dir_map[folder] = []
        dir_map[folder].append(f["path"])

    
    entry_names = {"main", "app", "index", "server", "__main__"}
    entry_points = [f["path"] for f in parsed_files if Path(f["path"]).stem.lower() in entry_names]

    
    import_counts: dict[str, int] = {}
    for f in parsed_files:
        for imp in f.get("imports", []):
            import_counts[imp] = import_counts.get(imp, 0) + 1
    top_deps = sorted(import_counts.items(), key=lambda x: -x[1])[:12]

    
    s = []
    s.append(f"# {repo_name}\n")
    s.append(f"> Auto-generated documentation from codebase analysis\n")

    
    s.append("## 📋 Overview\n")
    s.append(f"**{repo_name}** is a {primary_lang}-based project with {len(parsed_files)} files and {total_loc:,} lines of code.\n")

    s.append("| Metric | Value |")
    s.append("|--------|-------|")
    s.append(f"| **Total Files** | {len(parsed_files)} |")
    s.append(f"| **Lines of Code** | {total_loc:,} |")
    s.append(f"| **Primary Language** | {primary_lang} |")
    s.append(f"| **Languages** | {', '.join(f'{l} ({c})' for l, c in sorted(lang_counts.items(), key=lambda x: -x[1])[:6])} |")
    avg_cx = sum(f.get("complexity_score", 0) for f in parsed_files) / max(len(parsed_files), 1)
    s.append(f"| **Avg Complexity** | {avg_cx:.0%} |")
    total_funcs = sum(len(f.get("functions", [])) for f in parsed_files)
    total_classes = sum(len(f.get("classes", [])) for f in parsed_files)
    s.append(f"| **Total Functions** | {total_funcs} |")
    s.append(f"| **Total Classes** | {total_classes} |\n")

    
    s.append("## 🚀 Getting Started\n")
    s.append("### Prerequisites\n")
    
    if any(f["path"].endswith((".py", ".pyw")) for f in parsed_files):
        s.append("- Python 3.8+")
        if any("requirements" in f["path"].lower() for f in parsed_files):
            s.append("- pip (Python package manager)\n")
            s.append("### Installation\n")
            s.append("```bash")
            s.append("# Clone the repository")
            s.append(f"git clone <repository-url>")
            s.append(f"cd {repo_name}\n")
            s.append("# Install dependencies")
            s.append("pip install -r requirements.txt")
            s.append("```\n")
    if any(f["path"].endswith((".ts", ".tsx", ".js", ".jsx")) for f in parsed_files):
        s.append("- Node.js 18+")
        s.append("- npm or yarn\n")
        if any("package.json" in f["path"] for f in parsed_files):
            s.append("### Installation\n")
            s.append("```bash")
            s.append("# Clone the repository")
            s.append(f"git clone <repository-url>")
            s.append(f"cd {repo_name}\n")
            s.append("# Install dependencies")
            s.append("npm install")
            s.append("```\n")

    
    s.append("### Running the Project\n")
    if entry_points:
        for ep in entry_points[:3]:
            ext = Path(ep).suffix.lstrip(".")
            if ext == "py":
                s.append(f"```bash\npython {ep}\n```\n")
            elif ext in ("js", "ts"):
                s.append(f"```bash\nnode {ep}\n```\n")

    
    s.append("## 🗂️ Project Structure\n")
    s.append("```")
    for folder in sorted(dir_map.keys()):
        files = dir_map[folder]
        s.append(f"├── {folder}/ ({len(files)} files)")
        for fp in sorted(files)[:5]:
            s.append(f"│   ├── {Path(fp).name}")
        if len(files) > 5:
            s.append(f"│   └── ... +{len(files)-5} more")
    s.append("```\n")

    if entry_points:
        s.append("## 🚪 Entry Points\n")
        for ep in entry_points[:5]:
            pf = next((f for f in parsed_files if f["path"] == ep), None)
            desc = f" — {pf.get('language', '')} ({pf.get('loc', 0)} LOC)" if pf else ""
            s.append(f"- `{ep}`{desc}")
        s.append("")

    if top_deps:
        s.append("## 📦 Key Dependencies\n")
        s.append("| Dependency | Used By |")
        s.append("|-----------|---------|")
        for dep, count in top_deps:
            s.append(f"| `{dep}` | {count} file(s) |")
        s.append("")

    
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if nodes:
        edge_count: dict[str, int] = {}
        for e in edges:
            edge_count[e["source"]] = edge_count.get(e["source"], 0) + 1
            edge_count[e["target"]] = edge_count.get(e["target"], 0) + 1
        hubs = sorted(edge_count.items(), key=lambda x: -x[1])[:5]
        if hubs:
            s.append("## 🏗️ Architecture — Hub Files\n")
            s.append("These files have the most connections and are central to the architecture:\n")
            s.append("| File | Connections | Role |")
            s.append("|------|-----------|------|")
            for path, conns in hubs:
                pf = next((f for f in parsed_files if f["path"] == path), None)
                role = pf.get("language", "Module") if pf else "Module"
                s.append(f"| `{path}` | {conns} | {role} |")
            s.append("")

    
    s.append("## 🔑 Key Files\n")
    key_files = sorted(parsed_files, key=lambda f: -f.get("complexity_score", 0))[:8]
    for f in key_files:
        cx = f.get("complexity_score", 0)
        emoji = "🔴" if cx > 0.7 else "🟡" if cx > 0.4 else "🟢"
        funcs = f.get("functions", [])
        s.append(f"- {emoji} **`{f['path']}`** — {f.get('language', '?')}, {f.get('loc', 0)} LOC, complexity {cx:.0%}")
        if funcs:
            s.append(f"  - Functions: {', '.join(f'`{fn}()`' for fn in funcs[:5])}")
    s.append("")

    s.append("## 📄 License\n")
    s.append("See LICENSE file for details.\n")

    s.append("---\n*Generated by Codebase Intelligence Tool*")
    return "\n".join(s)


async def generate_readme(repo_name: str, parsed_files: list[dict], graph: dict, repo_dir: Path) -> dict:
    """Generate README with AI enhancement or fallback."""
    file_summary = "\n".join(
        f"- {f['path']} ({f.get('language','?')}, {f.get('loc',0)} LOC, complexity={f.get('complexity_score',0):.0%}, "
        f"functions=[{', '.join(f.get('functions',[])[:5])}])"
        for f in sorted(parsed_files, key=lambda x: -x.get("complexity_score", 0))[:25]
    )
    edges_summary = f"{len(graph.get('edges', []))} dependency edges between {len(graph.get('nodes', []))} modules"
    total_loc = sum(f.get('loc', 0) for f in parsed_files)

    
    dir_summary = {}
    for f in parsed_files:
        parts = f["path"].split("/")
        folder = parts[0] if len(parts) > 1 else "root"
        dir_summary[folder] = dir_summary.get(folder, 0) + 1
    dir_info = ", ".join(f"{k}/ ({v} files)" for k, v in sorted(dir_summary.items(), key=lambda x: -x[1])[:10])

    prompt = (
        f"Generate a professional, comprehensive README.md for the '{repo_name}' repository.\n\n"
        f"CODEBASE STATS:\n"
        f"- {len(parsed_files)} files, {total_loc:,} total LOC\n"
        f"- {edges_summary}\n"
        f"- Directories: {dir_info}\n\n"
        f"KEY FILES:\n{file_summary}\n\n"
        f"Generate a README that a developer would be proud to put on GitHub. Include ALL of these sections:\n\n"
        f"# Project Title with description\n\n"
        f"## 📋 Overview — What this project does and why it's useful\n\n"
        f"## 🚀 Getting Started\n"
        f"### Prerequisites — What needs to be installed\n"
        f"### Installation — Step-by-step setup commands in code blocks\n"
        f"### Running — How to start the project\n\n"
        f"## 🗂️ Project Structure — Directory tree with explanations\n\n"
        f"## 🏗️ Architecture — How the system is designed, data flow, design patterns\n\n"
        f"## 📦 Key Dependencies — Table with package names and their purpose\n\n"
        f"## 🔑 API Reference — Key functions/endpoints (if applicable)\n\n"
        f"## 🤝 Contributing — How to contribute to the project\n\n"
        f"## 📄 License\n\n"
        f"Use proper markdown with tables, code blocks, badges, and headers. "
        f"Make it look professional and GitHub-ready."
    )
    result, source = await route_prompt(prompt)
    if result:
        return {"readme": result, "source": source}
    return {"readme": _build_readme_fallback(repo_name, parsed_files, graph), "source": "fallback"}




def _build_refactor_fallback(file_path: str, parsed: dict, content: str, dead_exports: list[dict]) -> str:
    """Generate refactor suggestions from file metrics."""
    s = []
    cx = parsed.get("complexity_score", 0)
    loc = parsed.get("loc", 0)
    nesting = parsed.get("nesting_depth", 0)
    funcs = parsed.get("functions", [])
    classes = parsed.get("classes", [])
    imports = parsed.get("imports", [])
    lang = parsed.get("language", "Unknown")

    s.append(f"## 🔧 Refactor Report: `{file_path}`\n")
    s.append(f"**Language:** {lang} · **LOC:** {loc} · **Complexity:** {cx:.0%} · **Nesting:** {nesting}\n")

    
    issues = 0
    suggestions = []

    
    if loc > 300:
        issues += 2
        suggestions.append({
            "severity": "high",
            "title": "File Too Large — Split Into Modules",
            "detail": f"This file has **{loc} lines**. Files over 300 LOC become difficult to maintain, test, and review.",
            "action": "Split into multiple modules grouped by responsibility. For example:",
            "example": f"```\n# Before: {Path(file_path).name} ({loc} LOC)\n# After:\n#   {Path(file_path).stem}_core.{Path(file_path).suffix.lstrip('.')}  — core business logic\n#   {Path(file_path).stem}_utils.{Path(file_path).suffix.lstrip('.')} — helper functions\n#   {Path(file_path).stem}_types.{Path(file_path).suffix.lstrip('.')} — type definitions\n```",
        })
    elif loc > 150:
        issues += 1
        suggestions.append({
            "severity": "medium",
            "title": "File Growing Large",
            "detail": f"**{loc} lines** — approaching the threshold for maintainability issues.",
            "action": "Consider extracting utility functions into a separate module before it gets worse.",
        })

    
    if nesting > 4:
        issues += 2
        suggestions.append({
            "severity": "high",
            "title": "Deep Nesting — Use Guard Clauses",
            "detail": f"Max nesting depth is **{nesting}**. Deep nesting makes code hard to follow and test.",
            "action": "Refactor using early returns and guard clauses:",
            "example": f"```{lang.lower()}\n# Before (deeply nested):\ndef process(data):\n    if data:\n        if data.valid:\n            if data.ready:\n                return handle(data)\n\n# After (guard clauses):\ndef process(data):\n    if not data:\n        return None\n    if not data.valid:\n        raise ValueError('Invalid data')\n    if not data.ready:\n        return None\n    return handle(data)\n```",
        })
    elif nesting > 3:
        issues += 1
        suggestions.append({
            "severity": "medium",
            "title": "Moderate Nesting",
            "detail": f"Nesting depth of **{nesting}** — watchful threshold.",
            "action": "Consider flattening with guard clauses or strategy pattern.",
        })

    
    if cx > 0.7:
        issues += 2
        suggestions.append({
            "severity": "high",
            "title": "High Complexity — Break Down Functions",
            "detail": f"Complexity is **{cx:.0%}** — in the danger zone. This makes the code error-prone and hard to test.",
            "action": "Break complex functions into smaller, single-responsibility units. Each function should do ONE thing.",
        })

    
    if len(funcs) > 12:
        issues += 1
        suggestions.append({
            "severity": "medium",
            "title": "Too Many Functions — Separate Concerns",
            "detail": f"**{len(funcs)} functions** in one file suggests mixed responsibilities.",
            "action": "Group related functions into separate modules or classes. Functions that share data should be in the same module.",
        })

    
    if len(imports) > 10:
        issues += 1
        suggestions.append({
            "severity": "medium",
            "title": "Heavy Import List — Reduce Coupling",
            "detail": f"**{len(imports)} imports** — this file depends on many other modules, making it fragile to changes.",
            "action": "Introduce a facade pattern or dependency injection to reduce direct coupling.",
        })

    
    file_dead = [d for d in dead_exports if d.get("path") == file_path]
    if file_dead:
        issues += 1
        symbols = ", ".join(f"`{d['symbol']}`" for d in file_dead[:5])
        suggestions.append({
            "severity": "medium",
            "title": "Unused Exports — Remove Dead Code",
            "detail": f"Dead symbols: {symbols}",
            "action": "Remove these unused exports or mark them as private (prefix with `_` in Python).",
        })

    
    lines = content.split("\n")
    todo_count = sum(1 for l in lines if any(t in l for t in ["TODO", "FIXME", "HACK", "XXX"]))
    if todo_count:
        suggestions.append({
            "severity": "low",
            "title": f"{todo_count} TODO/FIXME Markers",
            "detail": "Unfinished work tracked in code.",
            "action": "Address these items or create proper tickets in your issue tracker.",
        })

    if "print(" in content or "console.log(" in content:
        suggestions.append({
            "severity": "low",
            "title": "Debug Statements Present",
            "detail": "Found `print()` or `console.log()` calls.",
            "action": "Replace with a proper logging framework (`logging` module in Python, Winston/Pino in Node.js).",
        })

    
    has_error_handling = "try" in content and ("except" in content or "catch" in content)
    if not has_error_handling and loc > 30:
        suggestions.append({
            "severity": "medium",
            "title": "No Error Handling",
            "detail": "This file has no try/except or try/catch blocks.",
            "action": "Add error handling for I/O operations, network calls, and user input.",
        })

    
    has_type_hints = "->" in content or ": str" in content or ": int" in content
    if not has_type_hints and lang.lower() in ("python", "typescript"):
        suggestions.append({
            "severity": "low",
            "title": "Missing Type Annotations",
            "detail": "No type hints found. Type annotations catch bugs early and improve IDE support.",
            "action": f"Add type annotations to function signatures and important variables.",
        })

    
    if not suggestions:
        s.append("✅ **No significant refactoring needed.** This file is well-structured.\n")
        s.append("**Metrics:**")
        s.append(f"- Lines: {loc} (within limits)")
        s.append(f"- Complexity: {cx:.0%} (low)")
        s.append(f"- Nesting: {nesting} (manageable)")
        s.append(f"- Functions: {len(funcs)} (reasonable)")
        return "\n".join(s)

    severity_emoji = {"high": "🔴", "medium": "🟡", "low": "🟢"}
    overall = "🔴 Needs Attention" if issues >= 4 else "🟡 Some Improvements Suggested" if issues >= 2 else "🟢 Minor Tweaks"
    s.append(f"**Overall:** {overall} ({len(suggestions)} suggestions)\n")

    for sg in suggestions:
        emoji = severity_emoji.get(sg["severity"], "⚪")
        s.append(f"### {emoji} {sg['title']}\n")
        s.append(f"{sg['detail']}\n")
        s.append(f"**→ Action:** {sg['action']}\n")
        if "example" in sg:
            s.append(f"{sg['example']}\n")

    return "\n".join(s)


async def get_refactor_suggestions(file_path: str, parsed: dict, content: str, dead_exports: list[dict]) -> dict:
    """Get refactor suggestions with AI or fallback."""
    lang = parsed.get("language", "Unknown")
    prompt = (
        f"You are a senior code reviewer performing an expert-level refactoring analysis.\n\n"
        f"FILE: {file_path}\n"
        f"LANGUAGE: {lang}\n"
        f"METRICS: LOC={parsed.get('loc',0)}, Complexity={parsed.get('complexity_score',0):.0%}, "
        f"Nesting={parsed.get('nesting_depth',0)}, Functions={len(parsed.get('functions',[]))}, "
        f"Imports={len(parsed.get('imports',[]))}\n\n"
        f"SOURCE CODE:\n```\n{content[:5000]}\n```\n\n"
    )
    if dead_exports:
        dead_for_file = [d for d in dead_exports if d.get("path") == file_path]
        if dead_for_file:
            prompt += f"DEAD CODE: {', '.join(d['symbol'] for d in dead_for_file[:10])}\n\n"

    prompt += (
        f"Provide SPECIFIC, ACTIONABLE refactoring suggestions with these sections:\n\n"
        f"## Overall Assessment\n"
        f"Rate the code quality and summarize the main issues.\n\n"
        f"## 🔴 Critical Issues (if any)\n"
        f"For each critical issue:\n"
        f"- Describe the problem with the SPECIFIC code pattern\n"
        f"- Show the current problematic code\n"
        f"- Show the refactored version\n\n"
        f"## 🟡 Improvements\n"
        f"For each improvement:\n"
        f"- Explain why the current approach is suboptimal\n"
        f"- Provide before/after code examples in fenced code blocks\n"
        f"- Explain the benefit of the change\n\n"
        f"## 🟢 Minor Suggestions\n"
        f"Style, naming, documentation improvements.\n\n"
        f"## ✨ Refactored Version\n"
        f"Provide the complete improved version of the most important function/section.\n\n"
        f"Be SPECIFIC — reference actual variable names, function names, and line patterns. "
        f"Every suggestion must have a concrete code example."
    )
    result, source = await route_prompt(prompt)
    if result:
        return {"suggestions": result, "source": source}
    return {"suggestions": _build_refactor_fallback(file_path, parsed, content, dead_exports), "source": "fallback"}




_SECRET_PATTERNS = [
    (re.compile(r'''(?:api[_-]?key|apikey|secret|token|password|passwd|pwd)\s*[:=]\s*['"][^'"]{8,}['"]''', re.I), "Hardcoded secret/credential"),
    (re.compile(r'''['"](?:sk-|pk_live_|pk_test_|rk_live_|ghp_|gho_|github_pat_|xoxb-|xoxp-|AKIA)[A-Za-z0-9_\-]{10,}['"]'''), "API key/token in source"),
    (re.compile(r'''(?:AWS_SECRET|aws_secret)\s*[:=]\s*['"][^'"]+['"]''', re.I), "AWS credential exposed"),
]

_VULN_PATTERNS = [
    (re.compile(r'\beval\s*\('), "eval() usage", "Arbitrary code execution risk. Use `ast.literal_eval()` or JSON parsing."),
    (re.compile(r'\bexec\s*\('), "exec() usage", "Dynamic code execution. Avoid unless absolutely necessary."),
    (re.compile(r'subprocess\.(?:call|run|Popen)\s*\(.*shell\s*=\s*True', re.S), "Shell injection risk", "Using `shell=True` with subprocess. Pass args as list instead."),
    (re.compile(r'os\.system\s*\('), "os.system() usage", "Use `subprocess.run()` with `shell=False` for safer execution."),
    (re.compile(r'pickle\.load'), "Unsafe deserialization", "Pickle can execute arbitrary code. Use JSON or msgpack for untrusted data."),
    (re.compile(r'yaml\.load\s*\([^)]*\)', re.S), "Unsafe YAML loading", "Use `yaml.safe_load()` instead of `yaml.load()`."),
    (re.compile(r'innerHTML\s*='), "innerHTML assignment", "XSS risk. Use `textContent` or sanitize input."),
    (re.compile(r'dangerouslySetInnerHTML'), "dangerouslySetInnerHTML", "React XSS vector. Sanitize all input with DOMPurify."),
    (re.compile(r'document\.write\s*\('), "document.write()", "DOM injection risk. Use DOM manipulation APIs."),
    (re.compile(r'SELECT\s+.*\+\s*[\'\"]?\s*\+?\s*(?:req|request|input|params)', re.I), "SQL injection risk", "Concatenated SQL query. Use parameterized queries."),
    (re.compile(r"password.*=.*[\"'][^\"']{3,}[\"']", re.I), "Hardcoded password", "Move to environment variables or secret manager."),
    (re.compile(r'\.query\s*\(\s*[\'"`].*\$\{'), "Template literal SQL injection", "String interpolation in SQL. Use parameterized queries."),
    (re.compile(r'cors\s*\(\s*\)'), "Unrestricted CORS", "CORS with no origin restriction. Specify allowed origins."),
    (re.compile(r'verify\s*=\s*False', re.I), "SSL verification disabled", "Disabling SSL verification exposes to MITM attacks."),
    (re.compile(r'DEBUG\s*=\s*True', re.I), "Debug mode enabled", "Debug mode in production exposes stack traces and sensitive info."),
]

_HEADER_PATTERNS = [
    (re.compile(r'Access-Control-Allow-Origin.*\*'), "Wildcard CORS", "Restrict to specific origins in production."),
]


def scan_security(parsed_files: list[dict], repo_dir: Path) -> dict:
    """Scan all files for security issues. Returns structured findings with recommendations."""
    findings: list[dict] = []
    files_scanned = 0
    files_with_issues = set()

    scannable_exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rb", ".php", ".rs", ".env", ".yml", ".yaml", ".json"}

    for f in parsed_files:
        ext = Path(f["path"]).suffix.lower()
        if ext not in scannable_exts:
            continue

        fpath = repo_dir / f["path"]
        if not fpath.exists():
            continue
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        files_scanned += 1
        lines = content.split("\n")

        
        for pattern, desc in _SECRET_PATTERNS:
            for i, line in enumerate(lines, 1):
                if pattern.search(line):
                    findings.append({
                        "file": f["path"],
                        "line": i,
                        "severity": "critical",
                        "category": "secret",
                        "title": desc,
                        "detail": f"Line {i}: potential secret in source code",
                        "fix": "Move to environment variable or .env file. Use python-dotenv or similar.",
                    })
                    files_with_issues.add(f["path"])

        
        for pattern, title, fix in _VULN_PATTERNS:
            for i, line in enumerate(lines, 1):
                if pattern.search(line):
                    findings.append({
                        "file": f["path"],
                        "line": i,
                        "severity": "high" if "injection" in title.lower() or "exec" in title.lower() else "medium",
                        "category": "vulnerability",
                        "title": title,
                        "detail": f"Line {i}: {line.strip()[:80]}",
                        "fix": fix,
                    })
                    files_with_issues.add(f["path"])

        
        for pattern, title, fix in _HEADER_PATTERNS:
            for i, line in enumerate(lines, 1):
                if pattern.search(line):
                    findings.append({
                        "file": f["path"],
                        "line": i,
                        "severity": "medium",
                        "category": "config",
                        "title": title,
                        "detail": f"Line {i}: {line.strip()[:80]}",
                        "fix": fix,
                    })
                    files_with_issues.add(f["path"])

    
    seen = set()
    deduped = []
    for f in findings:
        key = (f["file"], f["line"], f["title"])
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    deduped.sort(key=lambda x: severity_order.get(x["severity"], 4))

    score = max(0, round(1.0 - len(deduped) / max(files_scanned * 2, 1), 2))

    
    recommendations = _build_security_recommendations(deduped, parsed_files, files_scanned)

    return {
        "findings": deduped[:50],
        "summary": {
            "files_scanned": files_scanned,
            "files_with_issues": len(files_with_issues),
            "total_findings": len(deduped),
            "critical": sum(1 for f in deduped if f["severity"] == "critical"),
            "high": sum(1 for f in deduped if f["severity"] == "high"),
            "medium": sum(1 for f in deduped if f["severity"] == "medium"),
            "low": sum(1 for f in deduped if f["severity"] == "low"),
            "security_score": score,
        },
        "recommendations": recommendations,
    }


def _build_security_recommendations(findings: list[dict], parsed_files: list[dict], files_scanned: int) -> list[dict]:
    """Build actionable security recommendations based on findings and codebase analysis."""
    recs = []

    
    categories = {}
    for f in findings:
        cat = f.get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1

    
    if categories.get("secret", 0) > 0:
        recs.append({
            "priority": "critical",
            "title": "🔐 Implement Secret Management",
            "description": "Hardcoded secrets were found in your source code. These will be exposed if the repository is public.",
            "steps": [
                "Move ALL secrets (API keys, passwords, tokens) to a `.env` file",
                "Add `.env` to your `.gitignore` file immediately",
                "Use `python-dotenv` (Python) or `dotenv` (Node.js) to load environment variables",
                "For production, use a secret manager like AWS Secrets Manager, HashiCorp Vault, or GitHub Secrets",
                "Rotate any secrets that may have been committed to version control",
            ],
        })

    
    has_auth = any("auth" in f["path"].lower() or "login" in f["path"].lower() for f in parsed_files)
    if not has_auth:
        recs.append({
            "priority": "high",
            "title": "🔑 Add Authentication & Authorization",
            "description": "No authentication module was detected. Ensure all sensitive endpoints require authentication.",
            "steps": [
                "Implement JWT or session-based authentication for your API",
                "Add role-based access control (RBAC) for different user types",
                "Use bcrypt or argon2 for password hashing (never store plaintext)",
                "Implement rate limiting to prevent brute-force attacks",
                "Add CSRF protection for form submissions",
            ],
        })

    
    if categories.get("vulnerability", 0) > 0:
        recs.append({
            "priority": "high",
            "title": "🛡️ Fix Code Vulnerabilities",
            "description": f"{categories['vulnerability']} vulnerability patterns were found that could be exploited.",
            "steps": [
                "Replace `eval()` and `exec()` with safe alternatives like `ast.literal_eval()` or JSON parsing",
                "Use parameterized queries for ALL database operations — never concatenate user input into SQL",
                "Sanitize HTML output with DOMPurify (frontend) or bleach (Python) to prevent XSS",
                "Use `subprocess.run()` with `shell=False` and pass args as a list",
                "Validate and sanitize ALL user input before processing",
            ],
        })

    
    has_https = any("https" in str(f.get("imports", [])).lower() for f in parsed_files)
    recs.append({
        "priority": "medium",
        "title": "📡 Secure Network Communication",
        "description": "Ensure all network communication is encrypted and validated.",
        "steps": [
            "Use HTTPS for all API endpoints in production",
            "Enable HSTS (HTTP Strict Transport Security) headers",
            "Set `Secure` and `HttpOnly` flags on all cookies",
            "Configure CORS with specific allowed origins (not wildcard `*`)",
            "Implement Content Security Policy (CSP) headers",
        ],
    })

    
    recs.append({
        "priority": "medium",
        "title": "📋 Add Input Validation",
        "description": "Validate all inputs at the API boundary to prevent injection and data corruption.",
        "steps": [
            "Use Pydantic (Python) or Zod/Joi (Node.js) for request validation",
            "Validate file upload types, sizes, and content",
            "Implement request size limits to prevent DoS",
            "Sanitize query parameters and path variables",
            "Add schema validation for JSON request bodies",
        ],
    })

    
    has_logging = any("logging" in str(f.get("imports", [])).lower() or "logger" in str(f.get("imports", [])).lower() for f in parsed_files)
    recs.append({
        "priority": "low",
        "title": "📊 Implement Security Logging & Monitoring",
        "description": "Track security-relevant events for incident detection and forensics.",
        "steps": [
            "Log authentication attempts (both success and failure)",
            "Monitor for unusual access patterns or rate spikes",
            "Set up alerts for critical security events",
            "Use structured logging (JSON format) for easy analysis",
            "Implement audit trails for sensitive data access",
        ],
    })

    
    has_deps = any("requirements" in f["path"].lower() or "package.json" in f["path"].lower() for f in parsed_files)
    if has_deps:
        recs.append({
            "priority": "medium",
            "title": "📦 Keep Dependencies Updated",
            "description": "Outdated dependencies often contain known vulnerabilities.",
            "steps": [
                "Run `pip audit` (Python) or `npm audit` (Node.js) regularly",
                "Set up Dependabot or Renovate for automatic dependency updates",
                "Pin dependency versions in production",
                "Review changelogs before major version upgrades",
                "Remove unused dependencies to reduce attack surface",
            ],
        })

    return recs




def _build_pr_review_fallback(
    parsed_files: list[dict],
    graph: dict,
    dead_code: dict,
    selected_files: list[str],
) -> str:
    """Generate a PR-style review for selected files using graph + metrics."""
    s = []
    s.append("## 📋 Pull Request Review\n")

    
    targets = []
    for path in selected_files:
        pf = next((f for f in parsed_files if f["path"] == path), None)
        if pf:
            targets.append(pf)

    if not targets:
        
        targets = sorted(parsed_files, key=lambda f: -f.get("complexity_score", 0))[:10]
        s.append("> *Full repository review — top 10 files by complexity*\n")
    else:
        s.append(f"> *Reviewing {len(targets)} selected file(s)*\n")

    
    total_loc = sum(f.get("loc", 0) for f in targets)
    avg_cx = sum(f.get("complexity_score", 0) for f in targets) / max(len(targets), 1)
    total_funcs = sum(len(f.get("functions", [])) for f in targets)
    total_classes = sum(len(f.get("classes", [])) for f in targets)

    s.append("### 📊 Summary\n")
    s.append("| Metric | Value |")
    s.append("|--------|-------|")
    s.append(f"| **Files** | {len(targets)} |")
    s.append(f"| **Total LOC** | {total_loc:,} |")
    s.append(f"| **Avg Complexity** | {avg_cx:.0%} |")
    s.append(f"| **Functions** | {total_funcs} |")
    s.append(f"| **Classes** | {total_classes} |")
    s.append("")

    
    edges = graph.get("edges", [])
    dep_count: dict[str, int] = {}
    dependant_count: dict[str, int] = {}
    for e in edges:
        dep_count[e["source"]] = dep_count.get(e["source"], 0) + 1
        dependant_count[e["target"]] = dependant_count.get(e["target"], 0) + 1

    
    dead_files = {d["path"] for d in dead_code.get("dead_files", [])}
    dead_exports_by_file: dict[str, list[str]] = {}
    for de in dead_code.get("dead_exports", []):
        dead_exports_by_file.setdefault(de["path"], []).append(de["symbol"])

    
    s.append("### ⚠️ Risk Assessment\n")
    risk_items = []
    high_risk_count = 0

    for f in targets:
        path = f["path"]
        cx = f.get("complexity_score", 0)
        loc = f.get("loc", 0)
        deps = dep_count.get(path, 0)
        dependants = dependant_count.get(path, 0)

        risks = []
        if cx > 0.7:
            risks.append(f"⚠️ complexity {cx:.0%}")
        if loc > 300:
            risks.append(f"⚠️ {loc} LOC (too large)")
        if dependants > 3:
            risks.append(f"🔗 {dependants} files depend on it")
        if path in dead_files:
            risks.append("🗑️ flagged as dead code")
        if path in dead_exports_by_file:
            risks.append(f"🗑️ {len(dead_exports_by_file[path])} unused exports")

        if risks:
            level = "🔴 HIGH" if (cx > 0.7 or dependants > 5) else "🟡 MEDIUM" if (cx > 0.4 or dependants > 2) else "🟢 LOW"
            if "HIGH" in level:
                high_risk_count += 1
            risk_items.append(f"- **{level}** `{path}` — {', '.join(risks)}")

    if risk_items:
        s.extend(risk_items)
    else:
        s.append("✅ No high-risk patterns detected.\n")
    s.append("")

    
    s.append("### 🔗 Impact Analysis\n")
    target_paths = {f["path"] for f in targets}
    affected = set()
    for e in edges:
        if e["source"] in target_paths:
            affected.add(e["target"])
        if e["target"] in target_paths:
            affected.add(e["source"])
    affected -= target_paths

    if affected:
        s.append(f"Changes to these files could affect **{len(affected)} other file(s)**:\n")
        for af in sorted(affected)[:10]:
            direction = "↓ imports from" if any(e["target"] == af for e in edges if e["source"] in target_paths) else "↑ imported by"
            s.append(f"- `{af}` — {direction} reviewed files")
        if len(affected) > 10:
            s.append(f"- *…and {len(affected) - 10} more*")
    else:
        s.append("These files have no external dependencies or dependants.")
    s.append("")

    
    s.append("### 📝 Per-File Review\n")
    for f in targets[:8]:
        path = f["path"]
        lang = f.get("language", "Unknown")
        cx = f.get("complexity_score", 0)
        loc = f.get("loc", 0)
        nesting = f.get("nesting_depth", 0)
        funcs = f.get("functions", [])

        emoji = "🔴" if cx > 0.7 else "🟡" if cx > 0.4 else "🟢"
        s.append(f"#### {emoji} `{path}`\n")
        s.append(f"**{lang}** · {loc} LOC · Complexity: {cx:.0%} · Nesting: {nesting} · {len(funcs)} functions\n")

        notes = []
        if cx > 0.7:
            notes.append("- ⚠️ **High complexity** — needs careful review. Consider breaking down before merging.")
        if nesting > 4:
            notes.append(f"- ⚠️ **Deep nesting (depth {nesting})** — refactor with guard clauses and early returns")
        if loc > 300:
            notes.append("- ⚠️ **Large file** — candidate for splitting into focused modules")
        if len(funcs) > 12:
            notes.append(f"- ⚠️ **{len(funcs)} functions** — possible mixed responsibilities, group by concern")
        if path in dead_exports_by_file:
            syms = ", ".join(f"`{s}`" for s in dead_exports_by_file[path][:3])
            notes.append(f"- 🗑️ **Unused exports:** {syms} — remove or mark as private")
        if dependant_count.get(path, 0) > 3:
            notes.append(f"- 🔗 **Hub file** — {dependant_count[path]} dependants, changes propagate widely. Test thoroughly.")
        if funcs:
            notes.append(f"- 📋 **Key functions:** {', '.join(f'`{fn}()`' for fn in funcs[:5])}")
        if not notes:
            notes.append("- ✅ **Looks good** — no concerns detected")
        s.extend(notes)
        s.append("")

    
    s.append("### 🏁 Verdict\n")
    if high_risk_count == 0:
        s.append("✅ **Approve** — No high-risk patterns detected. Standard review is sufficient.\n")
        s.append("**Checklist before merging:**")
        s.append("- [ ] All tests pass")
        s.append("- [ ] No new warnings introduced")
        s.append("- [ ] Documentation updated if needed")
    elif high_risk_count <= 2:
        s.append(f"🟡 **Approve with caution** — {high_risk_count} high-risk file(s) need extra scrutiny.\n")
        s.append("**Required before merging:**")
        s.append("- [ ] Review high-risk files carefully")
        s.append("- [ ] Add tests for changed functionality")
        s.append("- [ ] Verify no regression in dependent files")
    else:
        s.append(f"🔴 **Request changes** — {high_risk_count} high-risk files. Recommend refactoring before merge.\n")
        s.append("**Required changes:**")
        s.append("- [ ] Reduce complexity in red-flagged files")
        s.append("- [ ] Remove dead code and unused exports")
        s.append("- [ ] Add comprehensive tests")
        s.append("- [ ] Split oversized files")

    s.append("\n---\n*Generated by Codebase Intelligence Tool*")
    return "\n".join(s)


async def generate_pr_review(
    parsed_files: list[dict],
    graph: dict,
    dead_code: dict,
    selected_files: list[str],
    repo_name: str,
    repo_dir: Optional[Path] = None,
) -> dict:
    """Generate PR review with AI enhancement or fallback."""
    targets = [f for f in parsed_files if f["path"] in selected_files] if selected_files else sorted(
        parsed_files, key=lambda x: -x.get("complexity_score", 0)
    )[:10]

    file_summary = "\n".join(
        f"- {f['path']} ({f.get('language','?')}, {f.get('loc',0)} LOC, complexity={f.get('complexity_score',0):.0%}, "
        f"functions=[{', '.join(f.get('functions',[])[:5])}])"
        for f in targets
    )

    
    code_context = ""
    if repo_dir:
        for f in targets[:3]:
            try:
                fpath = repo_dir / f["path"]
                if fpath.exists():
                    content = fpath.read_text(encoding="utf-8", errors="ignore")[:2000]
                    code_context += f"\n\n--- {f['path']} ---\n```\n{content}\n```"
            except Exception:
                pass

    edges_info = f"{len(graph.get('edges', []))} dependency edges"
    dead_info = f"{len(dead_code.get('dead_files', []))} dead files, {len(dead_code.get('dead_exports', []))} dead exports"

    prompt = (
        f"You are a senior staff engineer performing a thorough PR/code review for '{repo_name}'.\n\n"
        f"FILES UNDER REVIEW:\n{file_summary}\n\n"
        f"DEPENDENCY GRAPH: {edges_info}\n"
        f"DEAD CODE ANALYSIS: {dead_info}\n"
    )
    if code_context:
        prompt += f"\nACTUAL SOURCE CODE:\n{code_context}\n"

    prompt += (
        f"\nProvide a detailed, actionable PR review with ALL of these sections:\n\n"
        f"## 📊 Change Summary\n"
        f"Overview of what these files do and their role in the system.\n\n"
        f"## ⚠️ Risk Assessment\n"
        f"For EACH file, assess the risk level (HIGH/MEDIUM/LOW) with specific reasons. "
        f"Consider complexity, number of dependants, and code patterns.\n\n"
        f"## 🔗 Impact Analysis\n"
        f"What other parts of the system could break if these files change? "
        f"List specific downstream effects.\n\n"
        f"## 🐛 Issues Found\n"
        f"List specific bugs, anti-patterns, security concerns, and performance issues. "
        f"Reference actual code patterns and function names.\n\n"
        f"## 📝 Per-File Review\n"
        f"For each file, provide:\n"
        f"- What it does and its quality assessment\n"
        f"- Specific concerns with code references\n"
        f"- Concrete suggestions for improvement\n\n"
        f"## 🏁 Verdict\n"
        f"✅ Approve / 🟡 Approve with caution / 🔴 Request changes\n"
        f"With a checklist of required actions before merge.\n\n"
        f"Be SPECIFIC and ACTIONABLE. Reference actual file names, function names, and code patterns. "
        f"Do NOT give generic review comments."
    )
    result, source = await route_prompt(prompt)
    if result:
        return {"review": result, "source": source}
    return {
        "review": _build_pr_review_fallback(parsed_files, graph, dead_code, selected_files),
        "source": "fallback",
    }
