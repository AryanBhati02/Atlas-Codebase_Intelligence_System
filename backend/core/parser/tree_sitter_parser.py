"""
tree_sitter_parser.py
---------------------
Tree-sitter (v0.21.x) based parser for Python, JavaScript, and TypeScript.
Produces FunctionNode dataclasses with full metadata for call-graph construction.

API note (tree-sitter 0.21.x):
    from tree_sitter import Language, Parser
    import tree_sitter_python as tspython
    language = Language(tspython.language())
    parser = Parser(); parser.set_language(language)
    parser.parse(bytes(content, "utf-8"))
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("codebase-intel.tree_sitter_parser")




Language: Any = None
TSParser: Any = None
_tspython: Any = None
_tsjavascript: Any = None
_tstypescript: Any = None

try:
    from tree_sitter import Language as Language, Parser as TSParser  

    _TS_AVAILABLE = True
except ImportError:  
    logger.warning("tree-sitter not installed — TreeSitterParser will return empty results.")
    _TS_AVAILABLE = False

try:
    import tree_sitter_python as _tspython  

    _PY_LANG_AVAILABLE = True
except ImportError:
    _PY_LANG_AVAILABLE = False
    logger.warning("tree-sitter-python not installed.")

try:
    import tree_sitter_javascript as _tsjavascript  

    _JS_LANG_AVAILABLE = True
except ImportError:
    _JS_LANG_AVAILABLE = False
    logger.warning("tree-sitter-javascript not installed.")

try:
    import tree_sitter_typescript as _tstypescript  

    _TS_LANG_AVAILABLE = True
except ImportError:
    _TS_LANG_AVAILABLE = False
    logger.warning("tree-sitter-typescript not installed.")







@dataclass
class FunctionNode:
    """Represents a single function or method extracted from source code."""

    id: str                          
    name: str                        
    file_path: str                   
    language: str                    
    line_start: int
    line_end: int
    parameters: list[str] = field(default_factory=list)
    return_type: str = ""
    docstring: str = ""
    calls_to: list[str] = field(default_factory=list)
    complexity: int = 1
    body_text: str = ""






_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        ".git",
        ".venv",
        "venv",
        "__snapshots__",
        "coverage",
        ".next",
    }
)

_SKIP_SUFFIXES: tuple[str, ...] = (
    ".min.js",
    ".min.css",
    ".bundle.js",
    ".chunk.js",
    ".map",
    ".d.ts",
)

_MAX_FILE_SIZE = 500 * 1024  


_PY_EXTS: frozenset[str] = frozenset({".py"})
_JS_EXTS: frozenset[str] = frozenset({".js", ".jsx", ".mjs", ".cjs"})
_TS_EXTS: frozenset[str] = frozenset({".ts", ".tsx"})


_PY_BRANCH_TYPES: frozenset[str] = frozenset(
    {
        "if_statement",
        "for_statement",
        "while_statement",
        "try_statement",
        "boolean_operator",
        "conditional_expression",
    }
)

_JS_BRANCH_TYPES: frozenset[str] = frozenset(
    {
        "if_statement",
        "for_statement",
        "while_statement",
        "catch_clause",
        "conditional_expression",
    }
)







def _node_text(node) -> str:
    """Return the decoded UTF-8 text of a tree-sitter node."""
    try:
        return node.text.decode("utf-8")
    except Exception:
        return ""


def _find_children_by_type(node, *types: str) -> list:
    """Return all immediate children matching any of *types*."""
    return [c for c in node.children if c.type in types]


def _find_descendants_by_type(node, *types: str) -> list:
    """DFS collect all descendant nodes matching any of *types*."""
    results: list = []
    stack = list(node.children)
    while stack:
        current = stack.pop()
        if current.type in types:
            results.append(current)
        stack.extend(current.children)
    return results


def _count_complexity(node, branch_types: frozenset[str]) -> int:
    """Count branch nodes in the subtree to compute cyclomatic complexity."""
    count = 0
    stack = list(node.children)
    while stack:
        n = stack.pop()
        if n.type in branch_types:
            count += 1
        
        if n.type == "binary_expression":
            op_child = n.child_by_field_name("operator")
            op_texts = [_node_text(op_child)] if op_child else []
            op_texts.extend(_node_text(child) for child in n.children)
            if any(op in ("&&", "||") for op in op_texts):
                count += 1
        stack.extend(n.children)
    return 1 + count  


def _make_language(language_capsule, name: str):
    """
    Build a tree-sitter Language from an installed grammar package.

    The requested packaged-grammar form is Language(grammar.language()). Some
    0.21.3 wheels still require the historical second name argument, so keep a
    compatibility fallback without using Language.build_library().
    """
    try:
        return Language(language_capsule())
    except TypeError:
        return Language(language_capsule(), name)


def _strip_python_string_literal(raw: str) -> str:
    """Best-effort cleanup for a Python string literal without using ast."""
    text = raw.strip()
    while text and text[0] in "rRuUbBfF":
        text = text[1:]

    for quote in ('"""', "'''", '"', "'"):
        if text.startswith(quote) and text.endswith(quote):
            return text[len(quote):-len(quote)].strip()

    return text.strip("\"'").strip()


def _extract_calls(body_node) -> list[str]:
    """
    Find all call_expression / call nodes in the subtree.
    Returns a de-duplicated list of called function/method names.
    """
    call_types = {"call_expression", "call"}
    seen: set[str] = set()
    results: list[str] = []

    stack = list(body_node.children)
    while stack:
        n = stack.pop()
        if n.type in call_types:
            
            callee = n.child_by_field_name("function") or (
                n.children[0] if n.children else None
            )
            if callee is not None:
                name = _resolve_callee_name(callee)
                if name and name not in seen:
                    seen.add(name)
                    results.append(name)
        stack.extend(n.children)

    return results


def _resolve_callee_name(callee_node) -> str:
    """
    Given the callee node of a call expression, return a name string.
    - Simple call: identifier → "func_name"
    - Method call: member_expression / attribute → "method_name"
    """
    t = callee_node.type
    if t == "identifier":
        return _node_text(callee_node)
    if t in ("member_expression", "subscript_expression"):
        
        prop = callee_node.child_by_field_name("property") or callee_node.child_by_field_name("attribute")
        if prop:
            return _node_text(prop)
    if t == "attribute":
        
        attr = callee_node.child_by_field_name("attribute")
        if attr:
            return _node_text(attr)
    
    text = _node_text(callee_node)
    return text.split(".")[-1] if "." in text else text







class TreeSitterParser:
    """
    Parse Python, JavaScript, and TypeScript files into FunctionNode objects
    using tree-sitter 0.21.x.
    """

    def __init__(self) -> None:
        self._parsers: dict[str, Any] = {}
        self._languages: dict[str, Any] = {}

        if not _TS_AVAILABLE:
            logger.error("tree-sitter is not installed; parsing will return no results.")
            return

        
        if _PY_LANG_AVAILABLE and _tspython is not None:
            try:
                py_lang = _make_language(_tspython.language, "python")
                py_parser = TSParser()
                py_parser.set_language(py_lang)
                for ext in _PY_EXTS:
                    self._parsers[ext] = py_parser
                    self._languages[ext] = py_lang
                logger.info("tree-sitter Python language loaded.")
            except Exception as exc:
                logger.warning(f"Failed to load tree-sitter Python: {exc}")

        
        if _JS_LANG_AVAILABLE and _tsjavascript is not None:
            try:
                js_lang = _make_language(_tsjavascript.language, "javascript")
                js_parser = TSParser()
                js_parser.set_language(js_lang)
                for ext in _JS_EXTS:
                    self._parsers[ext] = js_parser
                    self._languages[ext] = js_lang
                logger.info("tree-sitter JavaScript language loaded.")
            except Exception as exc:
                logger.warning(f"Failed to load tree-sitter JavaScript: {exc}")

        
        
        if _TS_LANG_AVAILABLE and _tstypescript is not None:
            try:
                ts_lang = _make_language(_tstypescript.language_typescript, "typescript")
                ts_parser = TSParser()
                ts_parser.set_language(ts_lang)

                tsx_lang = _make_language(_tstypescript.language_tsx, "tsx")
                tsx_parser = TSParser()
                tsx_parser.set_language(tsx_lang)

                self._parsers[".ts"] = ts_parser
                self._languages[".ts"] = ts_lang
                self._parsers[".tsx"] = tsx_parser
                self._languages[".tsx"] = tsx_lang
                logger.info("tree-sitter TypeScript/TSX language loaded.")
            except Exception as exc:
                logger.warning(f"Failed to load tree-sitter TypeScript: {exc}")

    
    
    

    def parse_file(self, file_path: str, content: str, language: str) -> list[FunctionNode]:
        """
        Parse *content* (source text) and return a list of FunctionNode objects.

        :param file_path: relative path within the repo (used for node IDs)
        :param content:   raw source code as a Python string
        :param language:  "python" | "javascript" | "typescript"
        """
        ext = Path(file_path).suffix.lower()
        parser = self._parsers.get(ext)
        if parser is None:
            return []

        if ext in _PY_EXTS:
            detected_language = "python"
        elif ext in _JS_EXTS:
            detected_language = "javascript"
        else:
            detected_language = "typescript"

        try:
            tree = parser.parse(bytes(content, "utf-8"))
        except Exception as exc:
            logger.warning(f"tree-sitter parse error in {file_path}: {exc}")
            return []

        if detected_language == "python":
            return self._extract_python_functions(tree.root_node, file_path, content)

        return self._extract_js_functions(
            tree.root_node,
            file_path,
            content,
            detected_language,
        )

    def parse_repository(self, repo_path: str) -> list[FunctionNode]:
        """
        Walk the repository directory tree and parse every eligible source file.
        Returns all FunctionNode objects collected.
        """
        all_nodes: list[FunctionNode] = []
        file_count = 0
        repo_root = Path(repo_path)

        for dirpath, dirnames, filenames in os.walk(repo_path):
            
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

            for filename in filenames:
                
                lower_name = filename.lower()
                if any(lower_name.endswith(s) for s in _SKIP_SUFFIXES):
                    continue

                full_path = Path(dirpath) / filename
                ext = full_path.suffix.lower()

                
                if ext not in self._parsers:
                    continue

                
                try:
                    if full_path.stat().st_size > _MAX_FILE_SIZE:
                        logger.debug(f"Skipping large file: {full_path}")
                        continue
                except OSError:
                    continue

                
                if ext in _PY_EXTS:
                    language = "python"
                elif ext in _JS_EXTS:
                    language = "javascript"
                else:
                    language = "typescript"

                
                try:
                    rel_path = str(full_path.relative_to(repo_root)).replace("\\", "/")
                except ValueError:
                    rel_path = str(full_path).replace("\\", "/")

                
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                except OSError as exc:
                    logger.warning(f"Cannot read {full_path}: {exc}")
                    continue

                try:
                    nodes = self.parse_file(rel_path, content, language)
                    all_nodes.extend(nodes)
                except Exception as exc:
                    logger.warning(f"Error parsing {full_path}: {exc}")
                    continue

                file_count += 1
                if file_count % 100 == 0:
                    logger.info(f"Progress: {file_count} files parsed, {len(all_nodes)} functions found.")

        logger.info(
            f"Repository parse complete: {file_count} files → {len(all_nodes)} functions."
        )
        return all_nodes

    
    
    

    def _extract_python_functions(
        self, root_node, file_path: str, content: str
    ) -> list[FunctionNode]:
        nodes: list[FunctionNode] = []
        lines = content.splitlines()

        def _process_node(node, class_name: Optional[str] = None) -> None:
            """Recursively walk AST, collecting function/class definitions."""
            actual_func_node = node

            
            if node.type == "decorated_definition":
                for child in node.children:
                    if child.type in ("function_definition", "async_function_definition"):
                        actual_func_node = child
                        break
                else:
                    
                    for child in node.children:
                        if child.type == "class_definition":
                            _process_class(child)
                    return

            if actual_func_node.type in ("function_definition", "async_function_definition"):
                _process_function(actual_func_node, class_name)

            elif node.type == "class_definition":
                _process_class(node)

            else:
                for child in node.children:
                    if child.type in (
                        "function_definition",
                        "async_function_definition",
                        "decorated_definition",
                        "class_definition",
                    ):
                        _process_node(child, class_name)

        def _process_class(class_node) -> None:
            name_node = class_node.child_by_field_name("name")
            cls_name = _node_text(name_node) if name_node else "UnknownClass"
            body = class_node.child_by_field_name("body")
            if body:
                for child in body.children:
                    if child.type in (
                        "function_definition",
                        "async_function_definition",
                        "decorated_definition",
                    ):
                        _process_node(child, cls_name)

        def _process_function(func_node, class_name: Optional[str]) -> None:
            name_node = func_node.child_by_field_name("name")
            if name_node is None:
                return
            func_name_raw = _node_text(name_node)
            display_name = f"{class_name}.{func_name_raw}" if class_name else func_name_raw

            
            params_node = func_node.child_by_field_name("parameters")
            parameters = _extract_py_params(params_node)

            
            return_type = ""
            ret_node = func_node.child_by_field_name("return_type")
            if ret_node:
                return_type = _node_text(ret_node).lstrip("->").strip()

            
            body_node = func_node.child_by_field_name("body")
            body_text = _node_text(body_node) if body_node else ""

            
            docstring = ""
            if body_node:
                for stmt in body_node.children:
                    if stmt.type == "expression_statement":
                        str_children = [
                            c for c in stmt.children if c.type == "string"
                        ]
                        if str_children:
                            raw = _node_text(str_children[0])
                            docstring = _strip_python_string_literal(raw)
                            break

            
            calls_to: list[str] = []
            if body_node:
                calls_to = _extract_calls(body_node)

            
            complexity = 1
            if body_node:
                complexity = _count_complexity(body_node, _PY_BRANCH_TYPES)

            line_start = func_node.start_point[0] + 1
            line_end = func_node.end_point[0] + 1

            node_id = f"{file_path}::{display_name}"
            nodes.append(
                FunctionNode(
                    id=node_id,
                    name=display_name,
                    file_path=file_path,
                    language="python",
                    line_start=line_start,
                    line_end=line_end,
                    parameters=parameters,
                    return_type=return_type,
                    docstring=docstring,
                    calls_to=calls_to,
                    complexity=complexity,
                    body_text=body_text,
                )
            )

        
        for child in root_node.children:
            _process_node(child)

        return nodes

    def _extract_js_functions(
        self, root_node, file_path: str, content: str, language: str
    ) -> list[FunctionNode]:
        nodes: list[FunctionNode] = []

        def _collect(node, class_name: Optional[str] = None) -> None:
            t = node.type

            if t == "class_declaration" or t == "class":
                cls_name_node = node.child_by_field_name("name")
                cls_name = _node_text(cls_name_node) if cls_name_node else "AnonymousClass"
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        _collect(child, cls_name)
                return

            if t == "function_declaration" or t == "generator_function_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    _process_js_func(node, _node_text(name_node), class_name, language)
                return

            if t == "method_definition":
                name_node = node.child_by_field_name("name")
                if name_node:
                    _process_js_func(node, _node_text(name_node), class_name, language)
                return

            if t == "lexical_declaration" or t == "variable_declaration":
                
                for declarator in _find_children_by_type(node, "variable_declarator"):
                    val = declarator.child_by_field_name("value")
                    if val and val.type in (
                        "arrow_function",
                        "function",
                        "function_expression",
                        "generator_function",
                    ):
                        name_node = declarator.child_by_field_name("name")
                        if name_node:
                            _process_js_func(val, _node_text(name_node), class_name, language, doc_node=node)
                return

            if t == "export_statement":
                
                for child in node.children:
                    _collect(child, class_name)
                return

            
            if t in (
                "program",
                "module",
                "statement_block",
                "export_default_declaration",
                "export_named_declaration",
            ):
                for child in node.children:
                    _collect(child, class_name)

        def _process_js_func(
            func_node,
            raw_name: str,
            class_name: Optional[str],
            lang: str,
            doc_node=None,
        ) -> None:
            display_name = f"{class_name}.{raw_name}" if class_name else raw_name

            
            params_node = func_node.child_by_field_name("parameters") or                          func_node.child_by_field_name("parameter")
            parameters = _extract_js_params(params_node)

            
            return_type = ""
            ret_node = func_node.child_by_field_name("return_type")
            if ret_node:
                return_type = _node_text(ret_node).lstrip(":").strip()

            
            body_node = func_node.child_by_field_name("body")
            body_text = _node_text(body_node) if body_node else ""

            
            docstring = _extract_jsdoc(doc_node or func_node)

            
            calls_to: list[str] = []
            if body_node:
                calls_to = _extract_calls(body_node)

            
            complexity = 1
            if body_node:
                complexity = _count_complexity(body_node, _JS_BRANCH_TYPES)

            line_start = func_node.start_point[0] + 1
            line_end = func_node.end_point[0] + 1

            node_id = f"{file_path}::{display_name}"
            nodes.append(
                FunctionNode(
                    id=node_id,
                    name=display_name,
                    file_path=file_path,
                    language=lang,
                    line_start=line_start,
                    line_end=line_end,
                    parameters=parameters,
                    return_type=return_type,
                    docstring=docstring,
                    calls_to=calls_to,
                    complexity=complexity,
                    body_text=body_text,
                )
            )

        _collect(root_node)
        return nodes







def _extract_py_params(params_node) -> list[str]:
    if params_node is None:
        return []
    names: list[str] = []
    for child in params_node.children:
        t = child.type
        if t == "identifier":
            names.append(_node_text(child))
        elif t in ("typed_parameter", "typed_default_parameter", "default_parameter"):
            
            for sub in child.children:
                if sub.type == "identifier":
                    names.append(_node_text(sub))
                    break
        elif t in ("list_splat_pattern", "dictionary_splat_pattern"):
            
            for sub in child.children:
                if sub.type == "identifier":
                    names.append("*" + _node_text(sub) if t == "list_splat_pattern" else "**" + _node_text(sub))
                    break
    return names


def _extract_js_params(params_node) -> list[str]:
    if params_node is None:
        return []
    names: list[str] = []
    for child in params_node.children:
        t = child.type
        if t == "identifier":
            names.append(_node_text(child))
        elif t in ("required_parameter", "optional_parameter"):
            pat = child.child_by_field_name("pattern")
            if pat:
                names.append(_node_text(pat))
        elif t in ("rest_pattern", "rest_element"):
            for sub in child.children:
                if sub.type == "identifier":
                    names.append("..." + _node_text(sub))
                    break
        elif t == "assignment_pattern":
            left = child.child_by_field_name("left")
            if left:
                names.append(_node_text(left))
    return names


def _extract_jsdoc(func_node) -> str:
    """Look for a block_comment or comment immediately preceding func_node in the parent's children."""
    parent = func_node.parent
    if parent is None:
        return ""
    prev_sibling = None
    for child in parent.children:
        if child == func_node:
            break
        prev_sibling = child

    if prev_sibling is None:
        return ""
    if prev_sibling.type in ("comment", "block_comment"):
        raw = _node_text(prev_sibling)
        
        stripped = raw.strip()
        if stripped.startswith("/**"):
            stripped = stripped[3:]
            if stripped.endswith("*/"):
                stripped = stripped[:-2]
        elif stripped.startswith("/*"):
            stripped = stripped[2:]
            if stripped.endswith("*/"):
                stripped = stripped[:-2]
        elif stripped.startswith("//"):
            stripped = stripped[2:]
        return stripped.strip()
    return ""
