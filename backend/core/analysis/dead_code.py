
import ast
import re
import json
from pathlib import Path

_ENTRY_PATTERNS = {
    "main.py", "app.py", "__main__.py", "__init__.py",
    "index.js", "index.ts", "index.tsx", "index.jsx",
    "main.js", "main.ts", "main.tsx",
    "App.js", "App.ts", "App.tsx", "App.jsx",
    "server.py", "server.js", "server.ts",
    "setup.py", "manage.py", "wsgi.py", "asgi.py",
    "vite.config.ts", "vite.config.js",
    "tailwind.config.js", "tailwind.config.ts",
    "postcss.config.js", "tsconfig.json", "package.json",
}

def _is_entry_point(path: str) -> bool:
    basename = Path(path).name
    return basename in _ENTRY_PATTERNS

def _extract_python_exports(content: str) -> list[str]:
    exports: list[str] = []
    try:
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple)):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                    exports.append(elt.value)
                            return exports

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    exports.append(node.name)
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    exports.append(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and not target.id.startswith("_"):
                        exports.append(target.id)
    except SyntaxError:
        pass
    return exports

_JS_EXPORT_PATTERNS = [
    
    re.compile(r'export\s+(?:default\s+)?(?:function|class|const|let|var)\s+(\w+)'),
    
    re.compile(r'export\s*\{([^}]+)\}'),
    
    re.compile(r'module\.exports\.(\w+)'),
    re.compile(r'module\.exports\s*=\s*\{([^}]+)\}'),
    
    re.compile(r'export\s+default\s+(\w+)'),
]

def _extract_js_exports(content: str) -> list[str]:
    exports: list[str] = []
    for pattern in _JS_EXPORT_PATTERNS:
        for match in pattern.finditer(content):
            val = match.group(1).strip()
            if ',' in val:
                
                for sym in val.split(','):
                    sym = sym.strip().split(' as ')[0].strip()
                    if sym and sym.isidentifier():
                        exports.append(sym)
            elif val.isidentifier():
                exports.append(val)
    return list(set(exports))

def _extract_python_imported_names(content: str) -> list[str]:
    names: list[str] = []
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.names:
                    for alias in node.names:
                        names.append(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    
                    parts = alias.name.split(".")
                    names.append(parts[-1])
    except SyntaxError:
        pass
    return names

_JS_IMPORT_NAME_PATTERNS = [
    
    re.compile(r'import\s*\{([^}]+)\}\s*from'),
    
    re.compile(r'import\s+(\w+)\s+from'),
    
    re.compile(r'(?:const|let|var)\s*\{([^}]+)\}\s*=\s*require'),
    
    re.compile(r'(?:const|let|var)\s+(\w+)\s*=\s*require'),
]

def _extract_js_imported_names(content: str) -> list[str]:
    names: list[str] = []
    for pattern in _JS_IMPORT_NAME_PATTERNS:
        for match in pattern.finditer(content):
            val = match.group(1).strip()
            if ',' in val:
                for sym in val.split(','):
                    sym = sym.strip().split(' as ')[-1].strip()
                    if sym and sym.isidentifier():
                        names.append(sym)
            elif val.isidentifier():
                names.append(val)
    return names

_PY_EXTS = {".py"}
_JS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

def analyze_dead_code(parsed_files: list[dict], repo_dir: Path) -> dict:
    
    export_index: dict[str, list[str]] = {}
    
    all_imported_names: set[str] = set()
    
    imported_modules: set[str] = set()

    for f in parsed_files:
        fpath = repo_dir / f["path"]
        if not fpath.exists():
            continue
        try:
            content = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        ext = Path(f["path"]).suffix.lower()

        if ext in _PY_EXTS:
            exports = _extract_python_exports(content)
            imported_names = _extract_python_imported_names(content)
        elif ext in _JS_EXTS:
            exports = _extract_js_exports(content)
            imported_names = _extract_js_imported_names(content)
        else:
            exports = []
            imported_names = []

        if exports:
            export_index[f["path"]] = exports

        all_imported_names.update(imported_names)

        for imp in f.get("imports", []):
            imported_modules.add(imp)

    dead_files: list[dict] = []
    dead_functions: list[dict] = []
    dead_exports: list[dict] = []

    from core.graph.graph_builder import _resolve_import, _build_basename_index

    all_paths = {f["path"] for f in parsed_files}
    basename_idx = _build_basename_index(all_paths)
    imported_file_paths: set[str] = set()
    for f in parsed_files:
        for imp in f.get("imports", []):
            target = _resolve_import(imp, f["path"], all_paths, basename_idx)
            if target:
                imported_file_paths.add(target)

    for f in parsed_files:
        path = f["path"]
        if _is_entry_point(path):
            continue
        if path not in imported_file_paths:
            dead_files.append({
                "path": path,
                "reason": "Never imported by any other file in the project",
            })

    dead_file_paths = {d["path"] for d in dead_files}
    for path, exports in export_index.items():
        if _is_entry_point(path):
            continue
        for symbol in exports:
            if symbol not in all_imported_names:
                dead_exports.append({
                    "path": path,
                    "symbol": symbol,
                })
                
                pf = next((f for f in parsed_files if f["path"] == path), None)
                if pf and symbol in pf.get("functions", []):
                    dead_functions.append({
                        "path": path,
                        "name": symbol,
                        "reason": f"Exported but never imported anywhere",
                    })

    summary = {
        "total_files": len(parsed_files),
        "dead_files_count": len(dead_files),
        "dead_functions_count": len(dead_functions),
        "dead_exports_count": len(dead_exports),
        "health_score": round(
            1.0 - (len(dead_files) / max(len(parsed_files), 1)), 2
        ),
    }

    return {
        "dead_files": dead_files,
        "dead_functions": dead_functions,
        "dead_exports": dead_exports,
        "summary": summary,
    }
