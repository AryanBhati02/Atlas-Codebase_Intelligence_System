
import ast
import re
from pathlib import Path

def _python_function_graph(content: str, file_path: str, all_imports: list[str]) -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    func_names: set[str] = set()

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {"nodes": [], "edges": []}

    lines = content.split("\n")
    total_lines = len(lines)

    func_defs: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end_line = node.end_lineno if hasattr(node, 'end_lineno') and node.end_lineno else node.lineno + 5
            line_count = end_line - node.lineno + 1

            complexity = 0
            for child in ast.walk(node):
                if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                                      ast.With, ast.Assert, ast.BoolOp)):
                    complexity += 1
            complexity_score = min(complexity / 10.0, 1.0)

            is_exported = not node.name.startswith("_")

            func_defs.append({
                "name": node.name,
                "start_line": node.lineno,
                "end_line": end_line,
                "line_count": line_count,
                "complexity": round(complexity_score, 2),
                "is_exported": is_exported,
                "ast_node": node,
            })
            func_names.add(node.name)

    for fd in func_defs:
        nodes.append({
            "id": f"{file_path}::{fd['name']}",
            "name": fd["name"],
            "start_line": fd["start_line"],
            "end_line": fd["end_line"],
            "line_count": fd["line_count"],
            "complexity": fd["complexity"],
            "is_exported": fd["is_exported"],
        })

    call_counter: dict[tuple[str, str], int] = {}
    for fd in func_defs:
        for node in ast.walk(fd["ast_node"]):
            if isinstance(node, ast.Call):
                callee_name = None
                is_cross = False
                if isinstance(node.func, ast.Name):
                    callee_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    callee_name = node.func.attr

                if callee_name:
                    if callee_name in func_names:
                        
                        edge_key = (fd["name"], callee_name)
                        call_counter[edge_key] = call_counter.get(edge_key, 0) + 1
                    elif callee_name in all_imports or callee_name[0].isupper():
                        
                        is_cross = True
                        edge_key = (fd["name"], callee_name)
                        call_counter[edge_key] = call_counter.get(edge_key, 0) + 1

    for (source, target), count in call_counter.items():
        is_cross = target not in func_names
        edges.append({
            "id": f"{file_path}::{source}-->{target}",
            "source_fn": source,
            "target_fn": target,
            "call_count": count,
            "is_cross_file": is_cross,
        })

    return {"nodes": nodes, "edges": edges}

_JS_FUNC_DEF_PATTERNS = [
    
    re.compile(r'(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+(\w+)\s*\(', re.MULTILINE),
    
    re.compile(r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[\w]+)\s*=>', re.MULTILINE),
    re.compile(r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function', re.MULTILINE),
]

_JS_CALL_PATTERN = re.compile(r'\b(\w+)\s*\(', re.MULTILINE)

def _js_function_graph(content: str, file_path: str, all_imports: list[str]) -> dict:
    nodes: list[dict] = []
    edges: list[dict] = []
    func_names: set[str] = set()

    lines = content.split("\n")

    func_defs: list[dict] = []
    seen_names: set[str] = set()

    for pattern in _JS_FUNC_DEF_PATTERNS:
        for match in pattern.finditer(content):
            name = match.group(1)
            if name in seen_names:
                continue
            seen_names.add(name)

            pos = match.start()
            line_num = content[:pos].count("\n") + 1

            end_line = line_num
            depth = 0
            started = False
            for i in range(line_num - 1, len(lines)):
                for ch in lines[i]:
                    if ch == '{':
                        depth += 1
                        started = True
                    elif ch == '}':
                        depth -= 1
                if started and depth <= 0:
                    end_line = i + 1
                    break
            else:
                end_line = min(line_num + 20, len(lines))

            line_count = max(end_line - line_num + 1, 1)
            complexity = min(line_count / 50.0, 1.0)

            is_exported = "export" in content[max(0, pos - 20):pos + len(match.group())]

            func_defs.append({
                "name": name,
                "start_line": line_num,
                "end_line": end_line,
                "line_count": line_count,
                "complexity": round(complexity, 2),
                "is_exported": is_exported,
            })
            func_names.add(name)

    for fd in func_defs:
        nodes.append({
            "id": f"{file_path}::{fd['name']}",
            "name": fd["name"],
            "start_line": fd["start_line"],
            "end_line": fd["end_line"],
            "line_count": fd["line_count"],
            "complexity": fd["complexity"],
            "is_exported": fd["is_exported"],
        })

    keywords = {"if", "for", "while", "switch", "catch", "return", "new",
                "throw", "typeof", "delete", "void", "class", "import", "export",
                "from", "const", "let", "var", "function", "async", "await"}

    call_counter: dict[tuple[str, str], int] = {}
    for fd in func_defs:
        body_start = fd["start_line"] - 1
        body_end = min(fd["end_line"], len(lines))
        body = "\n".join(lines[body_start:body_end])

        for match in _JS_CALL_PATTERN.finditer(body):
            callee = match.group(1)
            if callee == fd["name"]:
                continue  
            if callee in keywords:
                continue

            if callee in func_names or callee in all_imports:
                edge_key = (fd["name"], callee)
                call_counter[edge_key] = call_counter.get(edge_key, 0) + 1

    for (source, target), count in call_counter.items():
        is_cross = target not in func_names
        edges.append({
            "id": f"{file_path}::{source}-->{target}",
            "source_fn": source,
            "target_fn": target,
            "call_count": count,
            "is_cross_file": is_cross,
        })

    return {"nodes": nodes, "edges": edges}

_PY_EXTS = {".py"}
_JS_EXTS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

def build_function_graph(file_path: str, repo_dir: Path, parsed_file: dict) -> dict:
    fpath = repo_dir / file_path
    if not fpath.exists():
        return {"nodes": [], "edges": []}

    try:
        content = fpath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {"nodes": [], "edges": []}

    ext = Path(file_path).suffix.lower()
    all_imports = parsed_file.get("imports", [])

    import_names = []
    for imp in all_imports:
        parts = imp.split(".")
        import_names.append(parts[-1])
        if "/" in imp:
            import_names.append(imp.split("/")[-1])

    if ext in _PY_EXTS:
        return _python_function_graph(content, file_path, import_names)
    elif ext in _JS_EXTS:
        return _js_function_graph(content, file_path, import_names)
    else:
        return {"nodes": [], "edges": []}
