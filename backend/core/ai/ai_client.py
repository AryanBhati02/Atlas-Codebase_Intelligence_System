"""AI client — routes prompts through provider chain with template fallback.

Supports: file explanation, code analysis, beginner guide, Q&A.
All responses integrate with SQLite cache for instant repeat lookups.
Uses the AI router for multi-provider fallback: Ollama → Groq → Gemini → Mistral → HuggingFace.
"""

from pathlib import Path

from core.ai.router import route_prompt




def _fallback_explain(file_path: str, content: str, parsed: dict) -> str:
    lang = parsed.get("language", "Unknown")
    funcs = parsed.get("functions", [])
    classes = parsed.get("classes", [])
    imports = parsed.get("imports", [])
    loc = parsed.get("loc", 0)
    score = parsed.get("complexity_score", 0)
    nesting = parsed.get("nesting_depth", 0)

    sections = []
    sections.append(f"## 📄 File Overview\n")
    sections.append(f"**File:** `{file_path}`  ")
    sections.append(f"**Language:** {lang}  ")
    sections.append(f"**Lines of Code:** {loc}  ")
    sections.append(f"**Complexity Score:** {score:.0%}  ")
    sections.append(f"**Max Nesting Depth:** {nesting}\n")

    
    sections.append("### 🎯 Purpose & Responsibility\n")
    basename = Path(file_path).stem.lower()
    if "test" in basename:
        sections.append("This file contains **test cases** for validating functionality. It ensures correctness of the associated module by running assertions against expected outputs.\n")
    elif "config" in basename or "settings" in basename:
        sections.append("This is a **configuration file** that defines application settings, environment variables, and constants. It centralizes all configurable parameters so they can be changed without modifying core logic.\n")
    elif "__init__" in basename:
        sections.append("This is a **package initializer** that exports module-level symbols. It defines the public API of the package and controls what gets imported when the package is used.\n")
    elif "main" in basename or "app" in basename or "index" in basename:
        sections.append("This is an **entry point** file that bootstraps the application. It initializes dependencies, sets up routing/middleware, and starts the main execution loop.\n")
    elif "route" in basename or "api" in basename or "endpoint" in basename:
        sections.append("This file defines **API routes/endpoints** for handling HTTP requests. Each route maps a URL pattern to a handler function that processes the request and returns a response.\n")
    elif "model" in basename or "schema" in basename:
        sections.append("This file defines **data models/schemas** used across the application. These models validate, serialize, and structure data flowing through different layers of the system.\n")
    elif "util" in basename or "helper" in basename:
        sections.append("This is a **utility module** providing shared helper functions. These are reusable building blocks used by multiple parts of the codebase to avoid code duplication.\n")
    elif "service" in basename or "controller" in basename:
        sections.append("This file implements **business logic** in a service/controller pattern. It orchestrates data operations and enforces application rules between the API layer and data layer.\n")
    elif "middleware" in basename:
        sections.append("This file implements **middleware** that intercepts requests/responses in the processing pipeline. It handles cross-cutting concerns like authentication, logging, or error handling.\n")
    else:
        sections.append(f"This {lang} module provides core functionality for the project. It encapsulates domain-specific logic that other modules depend on.\n")

    
    if classes or funcs:
        sections.append("### 🏗️ Key Components\n")
        if classes:
            sections.append("**Classes:**")
            for cls in classes[:10]:
                sections.append(f"- `{cls}` — encapsulates related data and behavior")
            sections.append("")
        if funcs:
            sections.append("**Functions:**")
            for fn in funcs[:15]:
                sections.append(f"- `{fn}()` — handles specific processing logic")
            sections.append("")

    
    if imports:
        sections.append("### 📦 Dependencies & Imports\n")
        internal = [i for i in imports if not i.startswith(("os", "sys", "re", "json", "typing", "pathlib", "datetime", "collections", "abc", "functools", "itertools", "math", "hashlib", "uuid"))]
        stdlib = [i for i in imports if i not in internal]

        if internal:
            sections.append(f"**Project imports:** {', '.join(f'`{i}`' for i in internal[:10])}")
            sections.append("These are internal dependencies from other modules in this project.\n")
        if stdlib:
            sections.append(f"**Standard library:** {', '.join(f'`{i}`' for i in stdlib[:10])}")
            sections.append("These are Python/language standard library modules.\n")

    
    lines = content.split("\n")[:120]
    code_preview = "\n".join(lines)
    has_class = len(classes) > 0
    has_async = "async " in code_preview
    has_decorator = "@" in code_preview
    has_context_mgr = "with " in code_preview
    has_generator = "yield " in code_preview
    has_type_hints = "->" in code_preview or ": str" in code_preview or ": int" in code_preview
    has_error_handling = "try:" in code_preview or "except " in code_preview
    has_logging = "logging" in code_preview or "logger" in code_preview

    sections.append("### 🔄 Architecture & Design Patterns\n")
    notes = []
    if has_async:
        notes.append("- Uses **async/await** patterns for non-blocking I/O — enables concurrent request handling without threading")
    if has_decorator:
        notes.append("- Employs **decorators** for cross-cutting concerns like routing, caching, or access control")
    if has_class:
        notes.append(f"- Object-oriented design with **{len(classes)} class(es)** — encapsulates state and behavior together")
    if has_context_mgr:
        notes.append("- Uses **context managers** (`with` statements) for resource lifecycle management (files, connections, locks)")
    if has_generator:
        notes.append("- Implements **generators** for lazy evaluation — processes data on-demand without loading everything into memory")
    if has_type_hints:
        notes.append("- Includes **type annotations** for better IDE support, documentation, and static analysis")
    if has_error_handling:
        notes.append("- Has **error handling** with try/except blocks to gracefully manage failure scenarios")
    if has_logging:
        notes.append("- Uses a **logging framework** for structured debugging and monitoring output")
    if nesting > 3:
        notes.append(f"- ⚠️ Deep nesting (depth={nesting}) — consider extracting nested logic into separate helper methods")
    if loc > 200:
        notes.append(f"- ⚠️ Large file ({loc} LOC) — may benefit from splitting into smaller, focused modules")
    if not notes:
        notes.append("- Procedural/functional style with straightforward, linear control flow")
    sections.extend(notes)
    sections.append("")

    
    sections.append("### 🔀 Data Flow\n")
    if has_class and funcs:
        sections.append(f"Data flows through the **{len(classes)} class(es)** via **{len(funcs)} function(s)**. ")
        sections.append("Input is typically received through public methods, processed internally, and returned or stored.\n")
    elif funcs:
        sections.append(f"Data flows through **{len(funcs)} function(s)** in a pipeline pattern. ")
        sections.append("Each function transforms or validates data before passing it to the next step.\n")
    else:
        sections.append("This file primarily consists of top-level declarations and configurations.\n")

    
    sections.append("### 📊 Complexity Assessment\n")
    if score > 0.7:
        sections.append("⚠️ **High complexity** — this file has significant structural depth and size.\n")
        sections.append("**Recommended actions:**")
        sections.append("- Break complex functions into smaller, single-responsibility units (aim for <30 LOC per function)")
        sections.append("- Reduce nesting depth using early returns and guard clauses")
        sections.append("- Extract repeated logic into helper functions or utility modules")
        sections.append("- Consider the Strategy or Command pattern for complex conditional logic")
    elif score > 0.4:
        sections.append("🔶 **Moderate complexity** — manageable but requires attention during maintenance.\n")
        sections.append("**Watch for:**")
        sections.append("- Functions growing beyond 40-50 lines")
        sections.append("- Nesting depth exceeding 3 levels")
        sections.append("- Growing import list indicating coupling")
    else:
        sections.append("✅ **Low complexity** — clean, well-structured file that follows good practices.")
        sections.append("This file is easy to understand and maintain.")

    return "\n".join(sections)


async def explain_file(file_path: str, content: str, parsed: dict) -> dict:
    lang = parsed.get("language", "Unknown")
    funcs = parsed.get("functions", [])
    classes = parsed.get("classes", [])
    loc = parsed.get("loc", 0)
    imports = parsed.get("imports", [])
    complexity = parsed.get("complexity_score", 0)
    nesting = parsed.get("nesting_depth", 0)

    prompt = (
        f"You are a senior software architect providing a thorough, educational code explanation.\n\n"
        f"FILE: {file_path}\n"
        f"LANGUAGE: {lang}\n"
        f"LOC: {loc} | COMPLEXITY: {complexity:.0%} | NESTING DEPTH: {nesting}\n"
        f"FUNCTIONS: {', '.join(funcs[:20]) if funcs else 'None'}\n"
        f"CLASSES: {', '.join(classes[:10]) if classes else 'None'}\n"
        f"IMPORTS: {', '.join(imports[:15]) if imports else 'None'}\n\n"
        f"SOURCE CODE:\n```{lang.lower()}\n{content[:6000]}\n```\n\n"
        f"Provide a COMPREHENSIVE, DETAILED explanation with these sections:\n\n"
        f"## 🎯 Purpose & Responsibility\n"
        f"What this file does, why it exists, and its role in the larger system. Be specific, not generic.\n\n"
        f"## 🏗️ Architecture & Design Patterns\n"
        f"- What design patterns are used (e.g., Factory, Observer, Strategy, Middleware, Repository)?\n"
        f"- How does this file fit into the overall architecture (MVC, layered, microservices)?\n"
        f"- What principles does it follow (SOLID, DRY, separation of concerns)?\n\n"
        f"## 📋 Detailed Component Breakdown\n"
        f"For EACH class/function, explain:\n"
        f"- What it does (in 2-3 sentences minimum)\n"
        f"- What parameters it accepts and returns\n"
        f"- How it interacts with other components\n"
        f"- Any edge cases or important behavior\n\n"
        f"## 🔀 Data Flow\n"
        f"Trace how data moves through this file from input to output. Describe the transformation pipeline.\n\n"
        f"## 📦 Dependencies Analysis\n"
        f"- Why each major import is needed\n"
        f"- Internal vs external dependencies\n"
        f"- Coupling concerns\n\n"
        f"## ⚠️ Potential Issues & Improvements\n"
        f"- Performance bottlenecks\n"
        f"- Error handling gaps\n"
        f"- Security concerns\n"
        f"- Refactoring opportunities with specific suggestions\n\n"
        f"Use rich markdown formatting with headers, bold text, and code references."
    )
    result, source = await route_prompt(prompt)
    if result:
        return {"explanation": result, "source": source}
    return {"explanation": _fallback_explain(file_path, content, parsed), "source": "fallback"}




def _fallback_analyze(code: str, file_path: str) -> str:
    lines = code.strip().split("\n")
    line_count = len(lines)

    sections = []
    sections.append("## 🔍 Comprehensive Code Analysis\n")
    sections.append(f"**File:** `{file_path}`  ")
    sections.append(f"**Lines analyzed:** {line_count}\n")

    
    ext = Path(file_path).suffix.lstrip(".")
    lang_map = {
        "py": "python", "js": "javascript", "ts": "typescript",
        "tsx": "typescript", "jsx": "javascript", "go": "go",
        "rs": "rust", "java": "java", "rb": "ruby", "php": "php",
    }
    lang = lang_map.get(ext, "")
    sections.append(f"```{lang}")
    sections.append(code[:1200])
    sections.append("```\n")

    
    sections.append("### 📋 Code Purpose & Logic\n")

    has_loop = any(kw in code for kw in ["for ", "while ", ".forEach", ".map(", ".filter(", ".reduce("])
    has_error = any(kw in code for kw in ["try", "except", "catch", "throw", "raise"])
    has_return = "return " in code
    has_condition = any(kw in code for kw in ["if ", "else:", "else {", "elif ", "switch", "? "])
    has_class = any(kw in code for kw in ["class ", "Class ", "interface "])
    has_async = any(kw in code for kw in ["async ", "await ", "Promise", ".then("])
    has_import = any(kw in code for kw in ["import ", "require(", "from "])
    has_function_def = any(kw in code for kw in ["def ", "function ", "const ", "=> "])

    desc_parts = []
    if has_class:
        desc_parts.append("class/object definition with encapsulated state and methods")
    if has_async:
        desc_parts.append("asynchronous operations with async/await or Promise-based patterns")
    if has_loop:
        desc_parts.append("iterative data processing with loop constructs")
    if has_error:
        desc_parts.append("error handling and exception management")
    if has_condition:
        desc_parts.append("conditional business logic and branching")
    if has_return:
        desc_parts.append("computed value transformation and return")
    if not desc_parts:
        desc_parts.append("declarative configuration or data structure definition")

    sections.append(f"This code block implements **{', '.join(desc_parts)}**.\n")

    
    if has_function_def:
        func_lines = [l.strip() for l in lines if l.strip().startswith(("def ", "function ", "async def ", "async function "))]
        if func_lines:
            sections.append("**Functions/Methods defined:**")
            for fl in func_lines[:10]:
                name = fl.split("(")[0].replace("def ", "").replace("function ", "").replace("async ", "").strip()
                sections.append(f"- `{name}` — processes data and returns results")
            sections.append("")

    
    sections.append("### ⚠️ Issues & Risk Assessment\n")
    issues = []

    if not has_error and (has_loop or "open(" in code or "request" in code.lower() or "fetch(" in code.lower()):
        issues.append("- 🔴 **Missing error handling** — I/O, network, or file operations must be wrapped in try/except blocks to prevent crashes. Add specific exception types for better debugging.")

    if "eval(" in code or "exec(" in code:
        issues.append("- 🔴 **Security risk: eval()/exec()** — These execute arbitrary code and can be exploited for injection attacks. Use `ast.literal_eval()` for safe evaluation or JSON parsing.")

    if "password" in code.lower() and ("=" in code or ":" in code):
        issues.append("- 🔴 **Hardcoded credentials detected** — Move sensitive values to environment variables or a secrets manager.")

    nested_depth = 0
    max_nested = 0
    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        level = indent // 4 if indent > 0 else indent // 2
        max_nested = max(max_nested, level)
    if max_nested > 4:
        issues.append(f"- 🟡 **Deep nesting (level {max_nested})** — Extract inner logic into helper functions. Use guard clauses and early returns to reduce depth.")

    if code.count("  ") > 20 or code.count("\t") > 8:
        issues.append("- 🟡 **Complex indentation** — consider extracting deeply nested logic into separate, well-named helper functions")

    if any(v in code for v in ["TODO", "FIXME", "HACK", "XXX"]):
        todo_count = sum(1 for l in lines if any(t in l for t in ["TODO", "FIXME", "HACK", "XXX"]))
        issues.append(f"- 🟡 **{todo_count} TODO/FIXME markers** — Unfinished work that needs to be addressed or converted to tracked issues")

    if "print(" in code or "console.log(" in code:
        debug_count = sum(1 for l in lines if "print(" in l or "console.log(" in l)
        issues.append(f"- 🟡 **{debug_count} debug statements** — Replace `print()`/`console.log()` with a proper logging framework (e.g., Python `logging` module, Winston for Node.js)")

    if len(lines) > 50:
        issues.append(f"- 🟡 **Large code block ({line_count} lines)** — This exceeds the recommended 30-40 lines per function. Split into smaller, focused functions with descriptive names.")

    duplicate_lines = {}
    for l in lines:
        stripped = l.strip()
        if len(stripped) > 20:
            duplicate_lines[stripped] = duplicate_lines.get(stripped, 0) + 1
    duplicates = {k: v for k, v in duplicate_lines.items() if v > 1}
    if duplicates:
        issues.append(f"- 🟡 **{len(duplicates)} duplicated code patterns** — Extract repeated logic into reusable functions (DRY principle)")

    if not has_error and has_return:
        issues.append("- 🟢 **No input validation** — Consider adding parameter validation and type checking for robustness")

    if not issues:
        issues.append("- ✅ No critical issues detected — code follows reasonable patterns")
    sections.extend(issues)
    sections.append("")

    
    sections.append("### 💡 Improvement Suggestions\n")
    improvements = []
    if not has_error:
        improvements.append("1. **Add error handling** — Wrap risky operations in try/except with specific exception types and meaningful error messages")
    if has_loop and not any(kw in code for kw in ["break", "return"]):
        improvements.append("2. **Add early exit conditions** — Use `break` or `return` in loops when the target is found to avoid unnecessary iterations")
    if not has_async and ("request" in code.lower() or "fetch" in code.lower()):
        improvements.append("3. **Consider async/await** — Network operations block the main thread. Making them async improves responsiveness")
    if len(lines) > 30:
        improvements.append("4. **Extract helper functions** — Break this into 2-3 smaller functions, each handling one specific concern")
    if not any(kw in code for kw in ["#", "//", "/*", '"""', "'''"]):
        improvements.append("5. **Add documentation** — Add docstrings/comments explaining the 'why' behind complex logic")
    improvements.append("6. **Add type annotations** — Type hints improve IDE support, catch bugs early, and serve as documentation")
    if has_loop:
        improvements.append("7. **Consider list comprehension** — Simple loops can often be replaced with more readable comprehensions")
    sections.extend(improvements[:6])
    sections.append("")

    
    sections.append("### 🔧 Refactored Version\n")
    sections.append("*Connect an AI provider (Ollama, Groq, Gemini, etc.) for an AI-generated refactored version of this code with concrete improvements applied.*\n")

    return "\n".join(sections)


async def analyze_code(code: str, file_path: str) -> dict:
    lang = Path(file_path).suffix.lstrip(".")
    lang_map = {"py": "Python", "js": "JavaScript", "ts": "TypeScript", "tsx": "TypeScript/React", "jsx": "JavaScript/React", "go": "Go", "rs": "Rust", "java": "Java"}
    language = lang_map.get(lang, lang.upper() if lang else "Unknown")

    prompt = (
        f"You are an expert senior developer performing an in-depth code review.\n\n"
        f"FILE: {file_path}\n"
        f"LANGUAGE: {language}\n\n"
        f"CODE TO ANALYZE:\n```{lang}\n{code[:5000]}\n```\n\n"
        f"Provide a thorough, detailed code review with ALL of these sections:\n\n"
        f"## 📋 What This Code Does\n"
        f"Explain the purpose and logic flow in detail. Walk through the code step by step.\n\n"
        f"## 🐛 Bugs & Issues Found\n"
        f"List ALL bugs, logic errors, edge cases, race conditions, and potential crashes. "
        f"For EACH issue, explain WHY it's a problem and show the problematic line.\n\n"
        f"## ⚡ Performance Analysis\n"
        f"Identify performance bottlenecks, unnecessary allocations, O(n²) algorithms, "
        f"missing caching opportunities, and memory leaks.\n\n"
        f"## 🔒 Security Concerns\n"
        f"Check for injection vulnerabilities, hardcoded secrets, unsafe deserialization, "
        f"missing input validation, and XSS/CSRF risks.\n\n"
        f"## 💡 Concrete Improvements\n"
        f"For each issue found, provide a SPECIFIC fix with code examples. "
        f"Don't just say 'add error handling' — show the actual code.\n\n"
        f"## ✨ Refactored Code\n"
        f"Provide the complete improved version of this code in a code block. "
        f"Apply ALL the suggestions above. Add comments explaining changes.\n\n"
        f"Be specific and concrete. Reference actual variable names, line patterns, and functions. "
        f"Do NOT give generic advice."
    )
    result, source = await route_prompt(prompt)
    if result:
        return {"analysis": result, "source": source}
    return {"analysis": _fallback_analyze(code, file_path), "source": "fallback"}




def _build_beginner_guide(repo_name: str, parsed_files: list[dict], repo_dir: Path) -> dict:
    """Generate a structured beginner-friendly onboarding guide."""

    
    sorted_files = sorted(parsed_files, key=lambda f: f.get("complexity_score", 0), reverse=True)
    top_files = sorted_files[:5]

    
    entry_points = []
    for f in parsed_files:
        name = Path(f["path"]).stem.lower()
        if name in ("main", "app", "index", "server", "__main__"):
            entry_points.append(f["path"])
    if not entry_points:
        entry_points = [parsed_files[0]["path"]] if parsed_files else []

    
    lang_counts: dict[str, int] = {}
    for f in parsed_files:
        lang = f.get("language") or "Other"
        lang_counts[lang] = lang_counts.get(lang, 0) + 1
    primary_lang = max(lang_counts, key=lang_counts.get) if lang_counts else "Unknown"

    
    dirs: set[str] = set()
    dir_file_counts: dict[str, int] = {}
    for f in parsed_files:
        parts = f["path"].split("/")
        if len(parts) > 1:
            dirs.add(parts[0])
            dir_file_counts[parts[0]] = dir_file_counts.get(parts[0], 0) + 1

    
    sections = []
    sections.append(f"# 🚀 Beginner's Guide to `{repo_name}`\n")
    sections.append("*Your complete onboarding guide to understanding this codebase*\n")

    sections.append("## 📋 Project Overview\n")
    sections.append(f"This project contains **{len(parsed_files)} files** primarily written in **{primary_lang}**.")
    if len(lang_counts) > 1:
        other_langs = [f"{l} ({c})" for l, c in sorted(lang_counts.items(), key=lambda x: -x[1]) if l != primary_lang]
        sections.append(f" Other languages used: {', '.join(other_langs[:5])}.")
    sections.append("")
    total_loc = sum(f.get("loc", 0) for f in parsed_files)
    avg_complexity = sum(f.get("complexity_score", 0) for f in parsed_files) / max(len(parsed_files), 1)
    total_functions = sum(len(f.get("functions", [])) for f in parsed_files)
    total_classes = sum(len(f.get("classes", [])) for f in parsed_files)

    sections.append("| Metric | Value |")
    sections.append("|--------|-------|")
    sections.append(f"| Total Files | {len(parsed_files)} |")
    sections.append(f"| Total Lines of Code | {total_loc:,} |")
    sections.append(f"| Total Functions | {total_functions} |")
    sections.append(f"| Total Classes | {total_classes} |")
    sections.append(f"| Average Complexity | {avg_complexity:.0%} |")
    sections.append(f"| Primary Language | {primary_lang} |")
    sections.append("")

    
    sections.append("## 🚪 Entry Points — Where to Start\n")
    sections.append("These are the files that boot up the application. Start here to understand the high-level flow:\n")
    for i, ep in enumerate(entry_points[:3], 1):
        pf = next((f for f in parsed_files if f["path"] == ep), None)
        if pf:
            funcs = pf.get("functions", [])
            func_preview = f" — key functions: {', '.join(f'`{fn}()`' for fn in funcs[:3])}" if funcs else ""
            sections.append(f"{i}. **`{ep}`** ({pf.get('language', '?')}, {pf.get('loc', 0)} LOC){func_preview}")
        else:
            sections.append(f"{i}. **`{ep}`**")
    sections.append("")

    
    sections.append("## 🗂️ Project Structure\n")
    sections.append("Here's what each directory contains and its role:\n")
    dir_map: dict[str, list[dict]] = {}
    for f in parsed_files:
        parts = f["path"].split("/")
        folder = parts[0] if len(parts) > 1 else "root"
        if folder not in dir_map:
            dir_map[folder] = []
        dir_map[folder].append(f)

    dir_purposes = {
        "api": "API routes & endpoint handlers",
        "core": "Core business logic & algorithms",
        "models": "Data models, schemas & types",
        "utils": "Shared utility functions",
        "components": "UI components (frontend)",
        "store": "State management",
        "config": "Configuration & settings",
        "services": "Service layer & integrations",
        "tests": "Test suites",
        "public": "Static assets",
        "src": "Main source code",
        "lib": "Shared libraries",
        "middleware": "Request/response middleware",
        "hooks": "Custom React hooks",
        "styles": "CSS/styling files",
    }

    for folder in sorted(dir_map.keys()):
        files = dir_map[folder]
        purpose = dir_purposes.get(folder.lower(), "Project files")
        total_dir_loc = sum(f.get("loc", 0) for f in files)
        sections.append(f"- **`{folder}/`** — {purpose} ({len(files)} files, {total_dir_loc:,} LOC)")
    sections.append("")

    
    sections.append("## 🔑 Key Files to Understand\n")
    sections.append("These are the most critical files based on complexity, connectivity, and importance:\n")
    for i, f in enumerate(top_files, 1):
        score = f.get("complexity_score", 0)
        emoji = "🔴" if score > 0.7 else "🟡" if score > 0.4 else "🟢"
        funcs = f.get("functions", [])
        classes = f.get("classes", [])
        loc = f.get("loc", 0)
        lang = f.get("language", "")

        sections.append(f"### {i}. {emoji} `{f['path']}`\n")
        sections.append(f"**{lang}** · {loc} LOC · Complexity: {score:.0%}\n")
        if classes:
            sections.append(f"**Classes:** {', '.join(f'`{c}`' for c in classes[:5])}")
        if funcs:
            sections.append(f"**Functions:** {', '.join(f'`{fn}()`' for fn in funcs[:6])}")
        sections.append("")

    
    sections.append("## 📖 Recommended Reading Order\n")
    sections.append("Follow this path to understand the codebase efficiently:\n")
    reading_order = []
    
    for ep in entry_points[:2]:
        reading_order.append(ep)
    
    for f in parsed_files:
        name = Path(f["path"]).stem.lower()
        if name in ("config", "settings", "constants", "types", "schema", "models"):
            if f["path"] not in reading_order:
                reading_order.append(f["path"])
    
    mid_files = sorted(
        [f for f in parsed_files if f["path"] not in reading_order],
        key=lambda f: abs(f.get("complexity_score", 0) - 0.5)
    )
    for f in mid_files[:5]:
        reading_order.append(f["path"])

    step_labels = [
        "Start here — understand the application bootstrap",
        "Read this next — learn the configuration",
        "Core logic — understand the main functionality",
        "Supporting module — see how components interact",
        "Deep dive — explore complex logic",
    ]
    for i, path in enumerate(reading_order[:8], 1):
        label = step_labels[min(i-1, len(step_labels)-1)]
        sections.append(f"**Step {i}.** `{path}`")
        sections.append(f"   _{label}_\n")

    
    sections.append("## 🧩 Architecture Patterns\n")
    patterns = []
    has_models = any("model" in f["path"].lower() or "schema" in f["path"].lower() for f in parsed_files)
    has_routes = any("route" in f["path"].lower() or "api" in f["path"].lower() for f in parsed_files)
    has_services = any("service" in f["path"].lower() for f in parsed_files)
    has_components = any("component" in f["path"].lower() for f in parsed_files)
    has_store = any("store" in f["path"].lower() for f in parsed_files)

    if has_models and has_routes:
        patterns.append("- **MVC/Layered Architecture** — Models define data, routes handle requests, logic is separated")
    if has_services:
        patterns.append("- **Service Pattern** — Business logic is encapsulated in service modules")
    if has_components and has_store:
        patterns.append("- **Component + Store** — Frontend uses component architecture with centralized state management")
    if any("middleware" in f["path"].lower() for f in parsed_files):
        patterns.append("- **Middleware Pipeline** — Request/response processing uses middleware chain pattern")
    if not patterns:
        patterns.append("- **Simple/Flat Structure** — Files are organized by function without strict layering")
    sections.extend(patterns)
    sections.append("")

    
    sections.append("## 💡 Tips for New Contributors\n")
    sections.append("1. **Start with entry points** — Trace the execution flow from `main`/`app`/`index`")
    sections.append("2. **Read config first** — Understanding settings reveals how the app is configured")
    sections.append("3. **Follow imports** — When reading a file, open its imports to understand dependencies")
    sections.append(f"4. **Green 🟢 files first** — Files with <40% complexity are easy wins for building context")
    sections.append(f"5. **Red 🔴 files last** — High complexity files ({sum(1 for f in parsed_files if f.get('complexity_score', 0) > 0.7)} files) need the most background")
    sections.append("6. **Use the graph view** — Visualize how files connect to see the big picture")
    sections.append("7. **Ask Q&A** — Use the Q&A tab to ask specific questions about any part of the code")

    guide = "\n".join(sections)
    top_file_list = [{"path": f["path"], "complexity_score": f.get("complexity_score", 0)} for f in top_files]

    return {"guide": guide, "top_files": top_file_list, "source": "fallback"}


async def beginner_guide(repo_name: str, parsed_files: list[dict], repo_dir: Path) -> dict:
    """Generate beginner onboarding guide."""

    
    file_summary = "\n".join(
        f"- {f['path']} (lang={f.get('language')}, loc={f.get('loc', 0)}, complexity={f.get('complexity_score', 0):.0%}, "
        f"functions=[{', '.join(f.get('functions', [])[:5])}], classes=[{', '.join(f.get('classes', [])[:3])}])"
        for f in sorted(parsed_files, key=lambda x: -x.get("complexity_score", 0))[:25]
    )

    
    dir_summary = {}
    for f in parsed_files:
        parts = f["path"].split("/")
        folder = parts[0] if len(parts) > 1 else "root"
        dir_summary[folder] = dir_summary.get(folder, 0) + 1
    dir_info = ", ".join(f"{k}/ ({v} files)" for k, v in sorted(dir_summary.items(), key=lambda x: -x[1])[:10])

    total_loc = sum(f.get("loc", 0) for f in parsed_files)
    total_funcs = sum(len(f.get("functions", [])) for f in parsed_files)

    prompt = (
        f"You are a senior developer creating a comprehensive onboarding guide for a new team member.\n\n"
        f"REPOSITORY: {repo_name}\n"
        f"TOTAL FILES: {len(parsed_files)} | TOTAL LOC: {total_loc:,} | TOTAL FUNCTIONS: {total_funcs}\n"
        f"DIRECTORIES: {dir_info}\n\n"
        f"Key files (sorted by complexity):\n{file_summary}\n\n"
        f"Generate a thorough, beginner-friendly onboarding guide with ALL these sections:\n\n"
        f"## 📋 Project Overview\n"
        f"What this project does, its tech stack, and why it exists. Include a metrics table.\n\n"
        f"## 🚪 Entry Points\n"
        f"Where to start reading code. Explain what each entry point does.\n\n"
        f"## 🗂️ Project Structure\n"
        f"Explain each directory's purpose and responsibility.\n\n"
        f"## 🔑 Key Files Deep Dive\n"
        f"For the top 5 most important files, explain their role, key functions, and how they connect.\n\n"
        f"## 📖 Recommended Reading Order\n"
        f"A numbered step-by-step path with explanations of what you'll learn at each step.\n\n"
        f"## 🧩 Architecture & Design Patterns\n"
        f"Explain the overall architecture, design patterns used, and data flow.\n\n"
        f"## 💡 Tips for New Contributors\n"
        f"Practical advice for navigating and understanding this specific codebase.\n\n"
        f"Be specific to THIS project. Use actual file names, function names, and directory names. "
        f"Use markdown tables, bold text, and code formatting for readability."
    )

    result, source = await route_prompt(prompt)
    if result:
        top_files = sorted(parsed_files, key=lambda f: -f.get("complexity_score", 0))[:5]
        top_file_list = [{"path": f["path"], "complexity_score": f.get("complexity_score", 0)} for f in top_files]
        return {"guide": result, "top_files": top_file_list, "source": source}

    return _build_beginner_guide(repo_name, parsed_files, repo_dir)




def _find_relevant_files(question: str, parsed_files: list[dict], repo_dir: Path) -> list[dict]:
    """Find top 5 most relevant files for the question using keyword matching."""
    q_lower = question.lower()
    q_words = set(q_lower.replace("?", "").replace(",", "").replace(".", "").replace("'", "").split())

    
    stop = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for",
            "of", "and", "or", "but", "not", "with", "this", "that", "it", "how", "what",
            "where", "when", "why", "which", "who", "does", "do", "did", "can", "could",
            "would", "should", "will", "has", "have", "had", "i", "me", "my", "you", "your",
            "about", "tell", "explain", "show", "give", "make", "using", "used"}
    q_words -= stop

    scored = []
    for f in parsed_files:
        score = 0.0
        path_lower = f["path"].lower()
        stem = Path(f["path"]).stem.lower()

        
        for word in q_words:
            if word in stem:
                score += 5.0
            elif word in path_lower:
                score += 3.0

        
        lang = (f.get("language") or "").lower()
        if lang and lang in q_lower:
            score += 2.0

        
        for fn in f.get("functions", []):
            fn_lower = fn.lower()
            if fn_lower in q_lower:
                score += 6.0
            elif any(w in fn_lower for w in q_words):
                score += 4.0
        for cls in f.get("classes", []):
            cls_lower = cls.lower()
            if cls_lower in q_lower:
                score += 6.0
            elif any(w in cls_lower for w in q_words):
                score += 4.0

        
        for imp in f.get("imports", []):
            if any(w in imp.lower() for w in q_words):
                score += 2.0

        
        score += f.get("complexity_score", 0) * 0.5
        score += min(f.get("loc", 0) / 500, 1.0) * 0.5

        if score > 0:
            scored.append((f, score))

    
    scored.sort(key=lambda x: -x[1])
    return [item[0] for item in scored[:8]]


def _build_qa_answer(question: str, relevant_files: list[dict], repo_dir: Path) -> dict:
    """Build a structured answer from relevant files."""
    if not relevant_files:
        return {
            "answer": "I couldn't find files directly related to your question. Try:\n\n"
                      "- **Be more specific** — mention file names, function names, or features\n"
                      "- **Ask about structure** — \"What does the api/ directory do?\"\n"
                      "- **Ask about patterns** — \"How is authentication implemented?\"\n"
                      "- **Reference code** — \"What does the `route_prompt` function do?\"",
            "referenced_files": [],
            "source": "fallback",
        }

    sections = []
    sections.append(f"## 💬 Answer\n")

    
    q_lower = question.lower()

    if any(w in q_lower for w in ["how", "work", "flow", "process", "implement"]):
        sections.append(f"Here's a detailed breakdown of how this works based on the relevant source code:\n")
    elif any(w in q_lower for w in ["where", "find", "locate", "define", "declared"]):
        sections.append(f"Here's where the relevant code is located with explanations:\n")
    elif any(w in q_lower for w in ["what", "purpose", "role", "mean", "does"]):
        sections.append(f"Here's what these components do and their role in the system:\n")
    elif any(w in q_lower for w in ["why", "reason", "cause"]):
        sections.append(f"Here's the reasoning and context from the codebase:\n")
    else:
        sections.append(f"Based on the codebase analysis, here are the relevant findings:\n")

    refs = []
    for i, f in enumerate(relevant_files[:5], 1):
        path = f["path"]
        lang = f.get("language", "Unknown")
        funcs = f.get("functions", [])
        classes = f.get("classes", [])
        loc = f.get("loc", 0)
        score = f.get("complexity_score", 0)

        sections.append(f"### {i}. `{path}`\n")
        sections.append(f"**Language:** {lang} · **LOC:** {loc} · **Complexity:** {score:.0%}\n")

        
        try:
            full_path = repo_dir / path
            if full_path.exists():
                content = full_path.read_text(encoding="utf-8", errors="ignore")
                q_words = set(q_lower.replace("?", "").split()) - {"the", "a", "is", "how", "what", "where", "does", "do", "can"}
                
                relevant_lines = []
                for line_num, line in enumerate(content.split("\n"), 1):
                    line_lower = line.lower()
                    if any(w in line_lower for w in q_words):
                        relevant_lines.append((line_num, line))
                
                if relevant_lines:
                    ext = Path(path).suffix.lstrip(".")
                    lang_map = {"py": "python", "js": "javascript", "ts": "typescript", "tsx": "typescript"}
                    sections.append(f"**Relevant code:**")
                    sections.append(f"```{lang_map.get(ext, '')}")
                    for ln, line in relevant_lines[:8]:
                        sections.append(f"L{ln}: {line.rstrip()}")
                    sections.append("```\n")
                else:
                    first_lines = content.split("\n")[:8]
                    preview = "\n".join(l for l in first_lines if l.strip())
                    if preview:
                        ext = Path(path).suffix.lstrip(".")
                        lang_map = {"py": "python", "js": "javascript", "ts": "typescript", "tsx": "typescript"}
                        sections.append(f"```{lang_map.get(ext, '')}")
                        sections.append(preview[:500])
                        sections.append("```\n")
        except Exception:
            pass

        if classes:
            sections.append(f"**Classes:** {', '.join(f'`{c}`' for c in classes[:5])}")
        if funcs:
            sections.append(f"**Functions:** {', '.join(f'`{fn}()`' for fn in funcs[:8])}")
        sections.append("")

        refs.append({"path": path, "relevance_reason": f"Matched query keywords in file structure and content"})

    sections.append("---\n")
    sections.append("💡 **Tip:** Select specific code in the editor and use **Analyze Selection** for deeper analysis of any section.")

    return {
        "answer": "\n".join(sections),
        "referenced_files": refs,
        "source": "fallback",
    }


async def answer_question(question: str, parsed_files: list[dict], repo_dir: Path) -> dict:
    """Answer a question about the codebase with file references."""
    relevant = _find_relevant_files(question, parsed_files, repo_dir)

    
    if relevant:
        context_parts = []
        for f in relevant[:5]:
            try:
                fpath = repo_dir / f["path"]
                if fpath.exists():
                    content = fpath.read_text(encoding="utf-8", errors="ignore")[:3000]
                    funcs = f.get("functions", [])
                    classes = f.get("classes", [])
                    meta = f"Functions: {', '.join(funcs[:10])}\nClasses: {', '.join(classes[:5])}" if (funcs or classes) else ""
                    context_parts.append(f"File: {f['path']} ({f.get('language', '?')}, {f.get('loc', 0)} LOC)\n{meta}\n```\n{content}\n```")
            except Exception:
                pass

        context = "\n\n".join(context_parts)
        prompt = (
            f"You are a senior developer answering questions about a specific codebase. "
            f"You have access to the actual source code below.\n\n"
            f"QUESTION: {question}\n\n"
            f"RELEVANT SOURCE CODE:\n{context}\n\n"
            f"Answer the question thoroughly with:\n"
            f"1. **Direct answer** — Answer the question clearly and specifically in the first paragraph\n"
            f"2. **Code references** — Point to specific files, functions, and line patterns that are relevant. "
            f"Use `backticks` for file names and function names.\n"
            f"3. **Code examples** — Show relevant code snippets in fenced code blocks\n"
            f"4. **How it works** — Explain the mechanism/flow in detail\n"
            f"5. **Related context** — Mention related files, patterns, or concepts the developer should know\n\n"
            f"Be SPECIFIC to this codebase. Reference actual file names, function names, and code patterns. "
            f"Do NOT give generic programming advice. Use markdown formatting."
        )

        result, source = await route_prompt(prompt)
        if result:
            refs = [{"path": f["path"], "relevance_reason": "Matched query"} for f in relevant]
            return {"answer": result, "referenced_files": refs, "source": source}

    return _build_qa_answer(question, relevant, repo_dir)
