"""Extract the stored figure outputs from the instructor notebooks.

Reads the PNGs already embedded in the notebooks' cell outputs and writes them
to figures/session{1,2}/ under descriptive names. Nothing is re-executed, so
the images always match what the notebooks last produced.

Run from the repository root:

    python graph-workshop/figures/extract_figures.py

Existing PNGs are overwritten; the companion .txt descriptions are never
touched. If a notebook is re-run and a figure changes materially, update its
description by hand.
"""

import base64
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
NOTEBOOKS = ROOT / "notebooks"
FIGURES = ROOT / "figures"

# (cell index, output filename stem), in notebook order.
FIGURE_MAP = {
    "session1_instructor.ipynb": [
        (10, "01-spring-chain-normal-modes"),
        (24, "02-barbell-fiedler-vector-bottleneck"),
        (31, "03-ratiocut-vs-ncut-pendant-graph"),
        (32, "04-two-moons-kmeans-failure"),
        (34, "05-spectral-embedding-two-moons"),
        (35, "06-spectral-clustering-affinity-comparison"),
        (37, "07-eigengap-plot"),
        (41, "08-louvain-vs-planted-communities-confusion"),
        (46, "09-dublin-eds-third-level-education-choropleth"),
        (47, "10-queen-vs-rook-contiguity-graphs"),
        (49, "11-contiguity-graph-over-dublin-map"),
        (50, "12-betweenness-centrality-map"),
        (51, "13-fiedler-vector-geometry-only-map"),
        (52, "14-rathmines-ranelagh-street-network"),
        (56, "15-edge-attribute-difference-histogram"),
        (58, "16-weighted-fiedler-median-sigma-map"),
        (59, "17-sigma-sweep-three-panels"),
        (60, "18-unweighted-weighted-kmeans-cluster-comparison"),
    ],
    "session2_instructor.ipynb": [
        (10, "01-morans-i-permutation-histogram"),
        (12, "02-moran-scatterplot"),
        (14, "03-lisa-cluster-map"),
        (15, "04-lisa-bh-corrected-vs-session1-clusters"),
        (21, "05-diffusion-snapshots-five-times"),
        (22, "06-modal-amplitude-decay"),
        (24, "07-explicit-euler-stability-threshold"),
        (26, "08-diffusion-with-fiedler-boundary"),
        (37, "09-capstone-leakage-vs-null-distributions"),
        (40, "10-shuffled-attribute-geography-destroyed"),
    ],
}


def cell_pngs(cell):
    """Every image/png output on a cell, as raw bytes."""
    return [base64.b64decode(out["data"]["image/png"])
            for out in cell.get("outputs", [])
            if "image/png" in out.get("data", {})]


def main():
    written = 0
    for filename, figures in FIGURE_MAP.items():
        session = filename.split("_")[0]
        dest = FIGURES / session
        dest.mkdir(parents=True, exist_ok=True)

        notebook = json.loads((NOTEBOOKS / filename).read_text())
        for index, stem in figures:
            images = cell_pngs(notebook["cells"][index])
            if len(images) != 1:
                # The cell moved, or was re-run without producing its figure.
                # Fail loudly rather than write the wrong image under this name.
                raise SystemExit(
                    f"{filename} cell {index} ({stem}): expected 1 image, "
                    f"found {len(images)}. The notebook has changed - update "
                    f"FIGURE_MAP."
                )
            (dest / f"{stem}.png").write_bytes(images[0])
            written += 1

    print(f"{written} figures written to {FIGURES}")


if __name__ == "__main__":
    main()
