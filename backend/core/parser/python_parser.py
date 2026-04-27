"""Python parser using native ast module. Extracts imports, functions, classes, LOC, nesting."""

import ast
from pathlib import Path


def _nesting_depth(node: ast.AST, depth: int = 0) -> int:
    max_d = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.With, ast.Try,
                              ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                              ast.ExceptHandler, ast.Match)):
            max_d = max(max_d, _nesting_depth(child, depth + 1))
        else:
            max_d = max(max_d, _nesting_depth(child, depth))
    return max_d


def parse_python(content: str, file_path: str) -> dict:
    imports: list[str] = []
    functions: list[str] = []
    classes: list[str] = []
    nesting = 0

    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
        nesting = _nesting_depth(tree)
    except SyntaxError:
        pass

    lines = content.split("\n")
    loc = sum(1 for line in lines if line.strip() and not line.strip().startswith("#"))

    return {
        "path": file_path,
        "imports": imports,
        "functions": functions,
        "classes": classes,
        "loc": loc,
        "nesting_depth": nesting,
    }
