"""JS/TS parser using regex patterns. Extracts imports, functions, classes, LOC, nesting."""

import re

_IMPORT_PATTERNS = [
    re.compile(r'''import\s+.*?\s+from\s+['"](.+?)['"]'''),
    re.compile(r'''import\s+['"](.+?)['"]'''),
    re.compile(r'''require\s*\(\s*['"](.+?)['"]\s*\)'''),
    re.compile(r'''import\s*\(\s*['"](.+?)['"]\s*\)'''),
]

_FUNC_PATTERNS = [
    re.compile(r'''function\s+(\w+)'''),
    re.compile(r'''(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\(.*?\)\s*=>)'''),
    re.compile(r'''(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+(\w+)'''),
]

_CLASS_PATTERN = re.compile(r'''class\s+(\w+)''')


def _calc_nesting(content: str) -> int:
    max_depth = 0
    depth = 0
    in_str = False
    str_char = ""
    i = 0
    chars = content

    while i < len(chars):
        c = chars[i]
        if in_str:
            if c == str_char and (i == 0 or chars[i - 1] != "\\"):
                in_str = False
        elif c in ('"', "'", "`"):
            in_str = True
            str_char = c
        elif c == "/" and i + 1 < len(chars):
            if chars[i + 1] == "/":
                nl = chars.find("\n", i)
                i = nl if nl != -1 else len(chars)
            elif chars[i + 1] == "*":
                end = chars.find("*/", i + 2)
                i = end + 1 if end != -1 else len(chars)
        elif c == "{":
            depth += 1
            max_depth = max(max_depth, depth)
        elif c == "}":
            depth = max(0, depth - 1)
        i += 1
    return max_depth


def parse_js(content: str, file_path: str) -> dict:
    imports: list[str] = []
    functions: list[str] = []
    classes: list[str] = []

    for pattern in _IMPORT_PATTERNS:
        imports.extend(pattern.findall(content))

    seen_funcs: set[str] = set()
    for pattern in _FUNC_PATTERNS:
        for name in pattern.findall(content):
            if name not in seen_funcs:
                functions.append(name)
                seen_funcs.add(name)

    classes.extend(_CLASS_PATTERN.findall(content))

    lines = content.split("\n")
    loc = sum(1 for line in lines if line.strip() and not line.strip().startswith("//"))
    nesting = _calc_nesting(content)

    return {
        "path": file_path,
        "imports": imports,
        "functions": functions,
        "classes": classes,
        "loc": loc,
        "nesting_depth": nesting,
    }
