"""
umap_viz.py
-----------
UMAP visualization of GATv2 function embeddings stored in Qdrant.

Produces:
  1. Static PNG  — publication-quality dark-theme scatter (matplotlib)
  2. Interactive HTML — hoverable Plotly scatter (standalone, works in browser)
  3. Cluster analysis JSON — KMeans clustering + language purity metrics

Usage:
    cd backend
    python training/umap_viz.py --collection atlas_functions
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import umap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch

try:
    import plotly.graph_objects as go
except ImportError:
    go = None  # type: ignore[assignment]
    print("WARNING: plotly not installed — interactive HTML will be skipped.")
    print("  Install with: pip install plotly")

from qdrant_client import QdrantClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("umap_viz")

LANGUAGE_COLORS: dict[str, str] = {
    "python": "#3572A5",
    "javascript": "#F7DF1E",
    "typescript": "#3178C6",
    "java": "#B07219",
    "go": "#00ADD8",
    "rust": "#DEA584",
    "c": "#555555",
    "cpp": "#F34B7D",
    "ruby": "#CC342D",
    "unknown": "#888888",
}

def fetch_embeddings_from_qdrant(
    host: str = "localhost",
    port: int = 6333,
    collection: str = "atlas_functions",
) -> tuple[np.ndarray, list[dict]]:
    """
    Scroll *all* points out of ``collection`` and return
    ``(embeddings [N, dim], metadata_list)``.
    """
    client = QdrantClient(host=host, port=port)
    all_points: list = []
    offset = None

    while True:
        response = client.scroll(
            collection_name=collection,
            limit=100,
            offset=offset,
            with_vectors=True,
        )
        points, next_offset = response
        all_points.extend(points)
        if next_offset is None:
            break
        offset = next_offset

    if not all_points:
        raise RuntimeError(
            f"No points found in Qdrant collection '{collection}'. "
            "Have you indexed a repo yet?"
        )

    embeddings = np.array([p.vector for p in all_points], dtype=np.float32)
    metadata = [p.payload for p in all_points]
    return embeddings, metadata

def create_static_umap(
    embeddings: np.ndarray,
    metadata: list[dict],
    output_path: str = "eval/results/umap_visualization.png",
) -> np.ndarray:
    """
    Create a publication-quality static UMAP scatter plot.

    Returns the 2-D UMAP coordinates ``[N, 2]`` so callers can reuse them.
    """
    logger.info("Running UMAP (static) …")
    reducer = umap.UMAP(
        n_neighbors=15,
        min_dist=0.1,
        metric="cosine",
        random_state=42,
    )
    coords = reducer.fit_transform(embeddings)

    languages = [m.get("language", "unknown").lower() for m in metadata]
    complexities = np.array(
        [float(m.get("complexity", 1)) for m in metadata], dtype=np.float32
    )
    if complexities.max() > complexities.min():
        normed = (complexities - complexities.min()) / (
            complexities.max() - complexities.min()
        )
    else:
        normed = np.ones_like(complexities) * 0.3
    sizes = 8 + normed * 52

    colors = [LANGUAGE_COLORS.get(l, LANGUAGE_COLORS["unknown"]) for l in languages]

    fig, ax = plt.subplots(figsize=(14, 10))
    fig.patch.set_facecolor("#0f0f14")
    ax.set_facecolor("#0f0f14")

    ax.scatter(
        coords[:, 0],
        coords[:, 1],
        c=colors,
        s=sizes,
        alpha=0.7,
        edgecolors="white",
        linewidths=0.15,
        zorder=2,
    )

    top_indices = np.argsort(complexities)[-20:]
    for idx in top_indices:
        name = metadata[idx].get("name", "?")
        if len(name) > 25:
            name = name[:22] + "…"
        ax.annotate(
            name,
            xy=(coords[idx, 0], coords[idx, 1]),
            fontsize=6,
            color="#e0e0e0",
            alpha=0.85,
            ha="left",
            va="bottom",
            textcoords="offset points",
            xytext=(4, 4),
        )

    unique_langs = sorted(set(languages))
    legend_patches = [
        Patch(
            facecolor=LANGUAGE_COLORS.get(l, LANGUAGE_COLORS["unknown"]),
            edgecolor="white",
            linewidth=0.5,
            label=l.capitalize(),
        )
        for l in unique_langs
    ]
    legend = ax.legend(
        handles=legend_patches,
        loc="upper right",
        fontsize=9,
        framealpha=0.3,
        facecolor="#1a1a24",
        edgecolor="#333",
        labelcolor="#e0e0e0",
    )
    legend.get_frame().set_linewidth(0.5)

    ax.set_title(
        f"Atlas GATv2 Embedding Space — {len(embeddings)} Functions",
        fontsize=16,
        fontweight="bold",
        color="#e0e0e0",
        pad=18,
    )
    fig.text(
        0.5,
        0.92,
        "Functions clustered by behavioral similarity, colored by language",
        ha="center",
        fontsize=10,
        color="#999",
        style="italic",
    )

    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fig.savefig(output_path, dpi=200, bbox_inches="tight", facecolor="#0f0f14")
    plt.close(fig)
    logger.info(f"Static UMAP saved → {output_path}")
    return coords

def create_interactive_umap(
    embeddings: np.ndarray,
    metadata: list[dict],
    output_path: str = "eval/results/umap_interactive.html",
    coords: np.ndarray | None = None,
) -> None:
    """
    Create a standalone interactive HTML scatter plot with Plotly.

    If ``coords`` is provided, reuse them instead of re-running UMAP.
    """
    if go is None:
        logger.warning("plotly not installed — skipping interactive HTML.")
        return

    if coords is None:
        logger.info("Running UMAP (interactive) …")
        reducer = umap.UMAP(
            n_neighbors=15, min_dist=0.1, metric="cosine", random_state=42
        )
        coords = reducer.fit_transform(embeddings)

    languages = [m.get("language", "unknown").lower() for m in metadata]
    complexities = [float(m.get("complexity", 1)) for m in metadata]

    c_arr = np.array(complexities, dtype=np.float32)
    if c_arr.max() > c_arr.min():
        normed = (c_arr - c_arr.min()) / (c_arr.max() - c_arr.min())
    else:
        normed = np.ones_like(c_arr) * 0.3
    sizes_px = 4 + normed * 14

    fig = go.Figure()
    unique_langs = sorted(set(languages))

    for lang in unique_langs:
        mask = [i for i, l in enumerate(languages) if l == lang]
        if not mask:
            continue

        hover_texts = []
        for i in mask:
            m = metadata[i]
            doc = (m.get("docstring") or "—")[:200]
            hover_texts.append(
                f"<b>{m.get('name', '?')}</b><br>"
                f"File: {m.get('file_path', '?')}<br>"
                f"Language: {m.get('language', '?')}<br>"
                f"Complexity: {m.get('complexity', '?')}<br>"
                f"<i>{doc}</i>"
            )

        fig.add_trace(
            go.Scatter(
                x=coords[mask, 0].tolist(),
                y=coords[mask, 1].tolist(),
                mode="markers",
                name=lang.capitalize(),
                marker=dict(
                    size=[float(sizes_px[i]) for i in mask],
                    color=LANGUAGE_COLORS.get(lang, LANGUAGE_COLORS["unknown"]),
                    opacity=0.75,
                    line=dict(width=0.3, color="white"),
                ),
                text=hover_texts,
                hoverinfo="text",
            )
        )

    fig.update_layout(
        title=dict(
            text=(
                f"Atlas GATv2 Embedding Space — {len(embeddings)} Functions<br>"
                '<span style="font-size:12px;color:#999">'
                "Functions clustered by behavioral similarity, colored by language"
                "</span>"
            ),
            x=0.5,
            font=dict(size=18, color="#e0e0e0"),
        ),
        paper_bgcolor="#0f0f14",
        plot_bgcolor="#0f0f14",
        font=dict(color="#e0e0e0"),
        legend=dict(
            bgcolor="rgba(26,26,36,0.7)",
            bordercolor="#333",
            borderwidth=1,
            font=dict(size=11),
        ),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
        hovermode="closest",
        margin=dict(l=20, r=20, t=80, b=20),
    )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fig.write_html(output_path, include_plotlyjs="cdn")
    logger.info(f"Interactive UMAP saved → {output_path}")

def create_cluster_analysis(
    embeddings: np.ndarray,
    metadata: list[dict],
    coords: np.ndarray | None = None,
) -> dict:
    """
    Cluster the 2-D UMAP projection with KMeans, measure language purity,
    and derive a *behavioral grouping score*.

    Low language purity → model learned **behaviour**, not syntax.
    """
    from sklearn.cluster import KMeans

    if coords is None:
        reducer = umap.UMAP(
            n_neighbors=15, min_dist=0.1, metric="cosine", random_state=42
        )
        coords = reducer.fit_transform(embeddings)

    n_clusters = max(2, min(10, len(embeddings) // 10))
    logger.info(f"KMeans clustering (k={n_clusters}) …")

    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(coords)

    clusters: dict[str, dict] = {}
    for i in range(n_clusters):
        mask = labels == i
        cluster_meta = [m for m, is_in in zip(metadata, mask) if is_in]
        languages = [m.get("language", "unknown").lower() for m in cluster_meta]

        lang_counts: dict[str, int] = {}
        for lang in languages:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

        if languages:
            majority_lang = max(lang_counts, key=lang_counts.get)  # type: ignore[arg-type]
            purity = lang_counts[majority_lang] / len(languages)
        else:
            majority_lang = "unknown"
            purity = 0.0

        sample_names = [m.get("name", "?") for m in cluster_meta[:5]]

        clusters[f"cluster_{i}"] = {
            "size": int(mask.sum()),
            "majority_language": majority_lang,
            "language_distribution": lang_counts,
            "language_purity": round(purity, 3),
            "sample_functions": sample_names,
        }

    avg_purity = float(np.mean([c["language_purity"] for c in clusters.values()]))

    if avg_purity < 0.7:
        interpretation = (
            f"Average language purity: {avg_purity:.1%}. "
            "Functions cluster by behavior across languages — "
            "model learned semantic similarity."
        )
    else:
        interpretation = (
            f"Average language purity: {avg_purity:.1%}. "
            "Functions still cluster somewhat by language. "
            "Consider more training epochs or better pair generation."
        )

    return {
        "num_clusters": n_clusters,
        "num_functions": len(embeddings),
        "avg_language_purity": round(avg_purity, 3),
        "behavioral_grouping_score": round(1.0 - avg_purity, 3),
        "clusters": clusters,
        "interpretation": interpretation,
    }

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate UMAP visualizations of Atlas GATv2 embeddings."
    )
    p.add_argument(
        "--collection",
        default="atlas_functions",
        help="Qdrant collection name (default: atlas_functions)",
    )
    p.add_argument(
        "--host",
        default="localhost",
        help="Qdrant host (default: localhost)",
    )
    p.add_argument(
        "--port",
        type=int,
        default=6333,
        help="Qdrant port (default: 6333)",
    )
    p.add_argument(
        "--output_dir",
        default="eval/results",
        help="Output directory (default: eval/results)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out = args.output_dir
    os.makedirs(out, exist_ok=True)

    logger.info(
        f"Connecting to Qdrant at {args.host}:{args.port}, "
        f"collection='{args.collection}' …"
    )
    embeddings, metadata = fetch_embeddings_from_qdrant(
        host=args.host, port=args.port, collection=args.collection
    )
    print(f"\n✅  Fetched {len(embeddings)} embeddings from Qdrant\n")

    png_path = os.path.join(out, "umap_visualization.png")
    coords = create_static_umap(embeddings, metadata, output_path=png_path)
    print(f"📊  Static UMAP  → {png_path}")

    html_path = os.path.join(out, "umap_interactive.html")
    create_interactive_umap(
        embeddings, metadata, output_path=html_path, coords=coords
    )
    print(f"🌐  Interactive   → {html_path}")

    analysis = create_cluster_analysis(embeddings, metadata, coords=coords)
    json_path = os.path.join(out, "umap_analysis.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)
    print(f"🔬  Analysis JSON → {json_path}")

    print("\n" + "=" * 60)
    print("  CLUSTER ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"  Clusters         : {analysis['num_clusters']}")
    print(f"  Functions        : {analysis['num_functions']}")
    print(f"  Avg purity       : {analysis['avg_language_purity']:.1%}")
    print(f"  Behavioral score : {analysis['behavioral_grouping_score']:.1%}")
    print(f"\n  {analysis['interpretation']}")
    print()

    for cname, cdata in analysis["clusters"].items():
        print(
            f"  {cname:>12}  size={cdata['size']:>3}  "
            f"purity={cdata['language_purity']:.0%}  "
            f"majority={cdata['majority_language']:<12}  "
            f"samples={cdata['sample_functions'][:3]}"
        )

    print(f"\n✅  Visualizations saved to {out}/")
    print("=" * 60)


if __name__ == "__main__":
    main()
