
from pathlib import Path

def _build_basename_index(all_paths: set[str]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for p in all_paths:
        stem = Path(p).stem
        if stem not in index:
            index[stem] = []
        index[stem].append(p)
    return index

def _resolve_import(imp: str, source_path: str, all_paths: set[str], basename_idx: dict[str, list[str]]) -> str | None:
    source_dir = str(Path(source_path).parent).replace("\\", "/")
    if source_dir == ".":
        source_dir = ""

    if imp.startswith("."):
        parts = imp.split("/") if "/" in imp else [imp]
        if imp.startswith("../"):
            parent = str(Path(source_dir).parent).replace("\\", "/")
            base = parent + "/" + "/".join(parts[1:]) if parent != "." else "/".join(parts[1:])
        elif imp.startswith("./"):
            base = (source_dir + "/" + "/".join(parts[1:])) if source_dir else "/".join(parts[1:])
        else:
            base = (source_dir + "/" + imp.lstrip(".")) if source_dir else imp.lstrip(".")
        base = base.strip("/")
    else:
        
        base = imp.replace(".", "/")

    candidates = [
        base,
        base + ".py",
        base + ".js",
        base + ".ts",
        base + ".tsx",
        base + ".jsx",
        base + "/index.js",
        base + "/index.ts",
        base + "/index.tsx",
        base + "/__init__.py",
    ]

    for c in candidates:
        if c in all_paths:
            return c

    base_name = base.split("/")[-1] if "/" in base else base
    matches = basename_idx.get(base_name)
    if matches:
        return matches[0]

    return None

def build_graph(parsed_files: list[dict]) -> dict:
    all_paths = {f["path"] for f in parsed_files}
    basename_idx = _build_basename_index(all_paths)

    nodes = []
    edges = []
    edge_set: set[tuple[str, str]] = set()

    for f in parsed_files:
        nodes.append({
            "id": f["path"],
            "label": Path(f["path"]).name,
            "language": f.get("language"),
            "loc": f.get("loc", 0),
            "size_bytes": f.get("size_bytes", 0),
            "complexity_score": f.get("complexity_score", 0.0),
            "imports_count": len(f.get("imports", [])),
            "functions_count": len(f.get("functions", [])),
            "classes_count": len(f.get("classes", [])),
        })

        for imp in f.get("imports", []):
            target = _resolve_import(imp, f["path"], all_paths, basename_idx)
            if target and target != f["path"]:
                edge_key = (f["path"], target)
                if edge_key not in edge_set:
                    edge_set.add(edge_key)
                    edges.append({
                        "id": f"{f['path']}-->{target}",
                        "source": f["path"],
                        "target": target,
                    })

    return {"nodes": nodes, "edges": edges}
