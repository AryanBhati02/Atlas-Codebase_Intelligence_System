
def _normalize(value: float, values: list[float]) -> float:
    if not values:
        return 0.0
    min_v = min(values)
    max_v = max(values)
    if max_v == min_v:
        return 0.5
    return (value - min_v) / (max_v - min_v)

def score_files(parsed_files: list[dict]) -> list[dict]:
    if not parsed_files:
        return parsed_files

    all_loc = [f["loc"] for f in parsed_files]
    all_nesting = [f["nesting_depth"] for f in parsed_files]
    all_imports = [len(f["imports"]) for f in parsed_files]
    all_sizes = [f["size_bytes"] for f in parsed_files]

    for f in parsed_files:
        n_loc = _normalize(f["loc"], all_loc)
        n_nest = _normalize(f["nesting_depth"], all_nesting)
        n_imp = _normalize(len(f["imports"]), all_imports)
        n_size = _normalize(f["size_bytes"], all_sizes)

        score = n_loc * 0.3 + n_nest * 0.3 + n_imp * 0.2 + n_size * 0.2
        f["complexity_score"] = round(min(max(score, 0.0), 1.0), 3)

    return parsed_files
