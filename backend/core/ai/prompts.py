"""
Prompt builders for file-aware, context-specific AI analysis.

Each builder produces a prompt that includes actual file content and repository
context so the AI response is specific to THIS codebase — never generic advice.
"""

from pathlib import Path


def build_explain_prompt(file_data: dict) -> str:
    """
    Build an explanation prompt with actual file content and graph context.

    Expected keys in file_data:
      repo_name, file_path, language, loc, complexity_score, nesting_depth,
      functions (list[str]), classes (list[str]), imports (list[str]),
      imported_by (list[str]), content (str, first 2000 chars)
    """
    repo = file_data.get("repo_name", "this project")
    path = file_data.get("file_path", "unknown")
    lang = file_data.get("language", "Unknown")
    loc = file_data.get("loc", 0)
    score = file_data.get("complexity_score", 0)
    nesting = file_data.get("nesting_depth", 0)
    functions = file_data.get("functions", [])[:20]
    classes = file_data.get("classes", [])
    imports = file_data.get("imports", [])[:10]
    imported_by = file_data.get("imported_by", [])[:10]
    content = file_data.get("content", "")[:2000]

    sym_parts = [f"class {c}" for c in classes] + [f"def {f}()" for f in functions]
    symbols = ", ".join(sym_parts) if sym_parts else "None"

    hub_note = (
        f"⚠️ Hub file — {len(imported_by)} other files depend on it: "
        f"{', '.join(imported_by[:5])}"
        if imported_by
        else "Leaf module — nothing imports it directly."
    )

    return (
        f"You are a senior software architect analysing the '{repo}' codebase.\n"
        f"Answer SPECIFICALLY about this file. Do not give generic programming advice.\n\n"
        f"=== FILE METADATA ===\n"
        f"Path        : {path}\n"
        f"Language    : {lang}  |  LOC: {loc}  |  Complexity: {score:.0%}  |  Max nesting: {nesting}\n"
        f"Symbols     : {symbols}\n"
        f"Imports from: {', '.join(imports) if imports else 'None'}\n"
        f"Imported by : {hub_note}\n\n"
        f"=== FILE CONTENT (first 2 000 chars) ===\n"
        f"```{lang.lower()}\n{content}\n```\n\n"
        f"=== TASK ===\n"
        f"Write a SPECIFIC, DETAILED explanation of `{path}` with these sections:\n\n"
        f"## Purpose & Role\n"
        f"What does this file do? Why does `{repo}` need it? "
        f"What would break if it were removed?\n\n"
        f"## Component Breakdown\n"
        f"For EACH symbol listed above: what it does, what it accepts, what it returns, "
        f"and any non-obvious side effects. Use `inline code` for names.\n\n"
        f"## Data Flow\n"
        f"Trace exactly how data enters and exits this file. Name the transformation steps.\n\n"
        f"## Coupling & Dependencies\n"
        f"Why is each import needed? {hub_note} Explain the coupling implications.\n\n"
        f"## Issues & Improvement Opportunities\n"
        f"Point to SPECIFIC patterns in the code above that could be improved. "
        f"Reference actual line content — no generic advice.\n\n"
        f"Use markdown with headers and inline `code`. Be concise but complete."
    )


def build_security_prompt(file_data: dict, findings: list[dict]) -> str:
    """
    Build a security analysis prompt that includes the actual vulnerable code lines.

    file_data: parsed file info with 'content' key (full file text)
    findings:  list of {file, line, title, detail, fix, severity}
    """
    path = file_data.get("file_path", "unknown")
    lang = file_data.get("language", "Unknown")
    content_lines = file_data.get("content", "").split("\n")

    finding_blocks: list[str] = []
    for f in findings[:15]:
        line_num = f.get("line", 0)
        sev = f.get("severity", "medium").upper()
        title = f.get("title", "Unknown issue")
        pattern = f.get("detail", "")

        if 1 <= line_num <= len(content_lines):
            start = max(0, line_num - 2)
            end = min(len(content_lines), line_num + 2)
            ctx = "\n".join(
                f"{'→ ' if i + start + 1 == line_num else '  '}"
                f"L{start + i + 1}: {content_lines[start + i]}"
                for i in range(end - start)
            )
        else:
            ctx = pattern

        finding_blocks.append(
            f"[{sev}] {title}\n"
            f"  Triggered pattern: {pattern}\n"
            f"  Code context:\n{ctx}"
        )

    findings_str = "\n\n".join(finding_blocks) if finding_blocks else "No automated findings."
    file_content = file_data.get("content", "")[:3000]

    return (
        f"You are a security engineer reviewing `{path}` for vulnerabilities.\n\n"
        f"=== FILE INFO ===\n"
        f"Path: {path}  |  Language: {lang}\n\n"
        f"=== AUTOMATED SCANNER FINDINGS ===\n"
        f"{findings_str}\n\n"
        f"=== FILE CONTENT ===\n"
        f"```{lang.lower()}\n{file_content}\n```\n\n"
        f"=== TASK ===\n"
        f"For each automated finding provide:\n"
        f"1. **Severity** — justify critical/high/medium/low based on exploitability\n"
        f"2. **Exact vulnerable line** — quote the line number and the code\n"
        f"3. **Attack scenario** — concrete, specific attack (not a generic description)\n"
        f"4. **Step-by-step remediation** — actual replacement code, not \"use a safer API\"\n\n"
        f"Then scan the file content YOURSELF for security issues the scanner missed:\n"
        f"- Logic flaws (auth bypass, IDOR, missing ownership checks)\n"
        f"- Insecure defaults (DEBUG flags, open CORS, no rate limits)\n"
        f"- Data exposure (PII in logs, verbose error messages)\n"
        f"- Missing input validation\n\n"
        f"Format each finding as a `## [SEVERITY] Title` section."
    )


def build_refactor_prompt(selected_code: str, file_context: dict) -> str:
    """
    Build a refactor prompt with the exact selected code and 10 lines of surrounding context.

    file_context keys:
      file_path, language, imports (list[str]), complexity_score,
      content_before (str, 10 lines before), content_after (str, 10 lines after)
    """
    path = file_context.get("file_path", "unknown")
    lang = file_context.get("language", "Unknown")
    imports = file_context.get("imports", [])[:10]
    before = file_context.get("content_before", "")
    after = file_context.get("content_after", "")
    complexity = file_context.get("complexity_score", 0)

    return (
        f"You are a senior engineer doing a targeted refactoring of `{path}`.\n\n"
        f"=== FILE CONTEXT ===\n"
        f"Language: {lang}  |  File complexity: {complexity:.0%}\n"
        f"Existing imports: {', '.join(imports) if imports else 'None'}\n\n"
        f"=== 10 LINES BEFORE SELECTION ===\n"
        f"```{lang.lower()}\n{before}\n```\n\n"
        f"=== SELECTED CODE TO REFACTOR ===\n"
        f"```{lang.lower()}\n{selected_code}\n```\n\n"
        f"=== 10 LINES AFTER SELECTION ===\n"
        f"```{lang.lower()}\n{after}\n```\n\n"
        f"=== TASK ===\n"
        f"Refactor ONLY the selected code block. Do not touch surrounding code.\n\n"
        f"## Issues Found\n"
        f"List specific problems: bugs, inefficiencies, readability issues, "
        f"missing error handling, type-safety gaps. Quote the actual problematic code.\n\n"
        f"## Before / After\n"
        f"Show a clear before → after comparison in fenced code blocks. "
        f"Add brief inline comments explaining each change.\n\n"
        f"## Explanation\n"
        f"For each change: why the original was problematic and why the replacement is better.\n\n"
        f"## Risk Level\n"
        f"Rate the refactoring: LOW (pure cleanup) | MEDIUM (logic change) | HIGH (behaviour change).\n"
        f"List specific tests or assertions needed to verify correctness after applying this diff."
    )


def build_onboarding_prompt(repo_summary: dict) -> str:
    """
    Build a new-developer onboarding guide prompt with the full file tree and hub files.

    repo_summary keys:
      repo_name, file_tree (list[str]), top_imported (list[{path, count}]),
      entry_points (list[str]), total_files, total_loc, languages (dict),
      parsed_files (list[{path, language, loc, functions, classes, complexity_score}])
    """
    name = repo_summary.get("repo_name", "this project")
    file_tree = repo_summary.get("file_tree", [])
    top_imported = repo_summary.get("top_imported", [])
    entry_points = repo_summary.get("entry_points", [])
    total_files = repo_summary.get("total_files", 0)
    total_loc = repo_summary.get("total_loc", 0)
    languages = repo_summary.get("languages", {})
    parsed = repo_summary.get("parsed_files", [])

    tree_str = "\n".join(f"  {p}" for p in file_tree[:40])
    if len(file_tree) > 40:
        tree_str += f"\n  … +{len(file_tree) - 40} more"

    top_str = "\n".join(
        f"  {item['path']} — imported by {item['count']} files"
        for item in top_imported[:10]
    ) or "  (none detected)"

    ep_str = "\n".join(f"  {ep}" for ep in entry_points[:5]) or "  (none detected)"

    key_files = sorted(parsed, key=lambda f: -f.get("complexity_score", 0))[:10]
    key_str = "\n".join(
        f"  {f['path']} ({f.get('language','?')}, {f.get('loc',0)} LOC, "
        f"cx={f.get('complexity_score',0):.0%}, "
        f"fns=[{', '.join(f.get('functions',[])[:4])}])"
        for f in key_files
    )

    lang_str = ", ".join(
        f"{lang} ({cnt})" for lang, cnt in sorted(languages.items(), key=lambda x: -x[1])[:5]
    )

    return (
        f"You are writing an onboarding guide for a developer who just joined the '{name}' project.\n"
        f"Every section MUST reference actual file names from the tree below.\n\n"
        f"=== REPOSITORY OVERVIEW ===\n"
        f"Name: {name}  |  Files: {total_files}  |  LOC: {total_loc:,}\n"
        f"Languages: {lang_str}\n\n"
        f"=== FULL FILE TREE ===\n{tree_str}\n\n"
        f"=== ENTRY POINTS ===\n{ep_str}\n\n"
        f"=== TOP 10 MOST-IMPORTED FILES (hub files) ===\n{top_str}\n\n"
        f"=== TOP 10 FILES BY COMPLEXITY ===\n{key_str}\n\n"
        f"=== TASK ===\n"
        f"Write a SPECIFIC, ACTIONABLE onboarding guide for `{name}`:\n\n"
        f"## 1. What Is This Project?\n"
        f"Infer the project's purpose from the file names and structure. Be specific.\n\n"
        f"## 2. How To Run It\n"
        f"Based on entry points and file names, provide exact startup commands.\n\n"
        f"## 3. Recommended Reading Order\n"
        f"A numbered list of files to read, in order, with one sentence per file explaining "
        f"what it teaches. Start with entry points and config, build toward complex files.\n\n"
        f"## 4. Key Concepts In This Codebase\n"
        f"3–5 non-obvious patterns or conventions SPECIFIC to this project. "
        f"Reference actual file names. No generic advice.\n\n"
        f"## 5. Gotcha Patterns\n"
        f"3 things that would confuse a developer from a different codebase: "
        f"unusual design choices, surprising file locations, or non-standard conventions.\n\n"
        f"## 6. Where To Make Common Changes\n"
        f"If someone needs to: add a feature / fix a bug / change config / add a test — "
        f"which exact files should they open?\n\n"
        f"Do NOT give generic programming advice. Use exact file paths throughout."
    )


def build_qa_prompt(question: str, context: list[dict], history: list[dict]) -> str:
    """
    Build a Q&A prompt with relevant file excerpts and the last 5 conversation turns.

    context items:  {path, language, loc, content (excerpt), functions, classes, relevance_reason}
    history items:  {question, answer}
    """
    file_blocks: list[str] = []
    for item in context[:5]:
        path = item.get("path", "")
        lang = item.get("language", "")
        content = item.get("content", "")[:1500]
        funcs = item.get("functions", [])
        classes = item.get("classes", [])
        reason = item.get("relevance_reason", "matched query")

        meta_lines = []
        if classes:
            meta_lines.append(f"Classes: {', '.join(classes[:5])}")
        if funcs:
            meta_lines.append(f"Functions: {', '.join(funcs[:8])}")
        meta = "\n".join(meta_lines) + "\n" if meta_lines else ""

        file_blocks.append(
            f"--- {path} ({lang}) | {reason} ---\n"
            f"{meta}"
            f"```{lang.lower()}\n{content}\n```"
        )

    context_str = "\n\n".join(file_blocks) or "(No relevant files found)"

    hist_lines: list[str] = []
    for turn in history[-5:]:
        hist_lines.append(f"Q: {turn.get('question', '')}")
        answer_preview = (turn.get("answer", "") or "")[:300]
        hist_lines.append(f"A: {answer_preview}{'…' if len(turn.get('answer','')) > 300 else ''}")
    hist_str = "\n".join(hist_lines) or "(No prior conversation)"

    return (
        f"You are a developer expert on this codebase answering a colleague's question.\n\n"
        f"=== CONVERSATION HISTORY (last 5 turns) ===\n{hist_str}\n\n"
        f"=== RELEVANT FILE EXCERPTS ===\n{context_str}\n\n"
        f"=== CURRENT QUESTION ===\n{question}\n\n"
        f"=== TASK ===\n"
        f"## Direct Answer\n"
        f"Answer the question in 2–3 sentences. Be specific, not vague.\n\n"
        f"## Code Evidence\n"
        f"Quote the SPECIFIC lines from the excerpts that answer the question. "
        f"Use `file_path:line_number` citations.\n\n"
        f"## How It Works\n"
        f"Explain the mechanism in detail, naming actual functions and files.\n\n"
        f"## Related Context\n"
        f"What else should the developer know? Related files, edge cases, gotchas.\n\n"
        f"IMPORTANT: If the answer is not in the provided files, say so honestly. "
        f"Never invent code that isn't shown."
    )
