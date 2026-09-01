# Workshop figures

Every figure produced by the two instructor notebooks, extracted as a standalone
PNG with a companion `.txt` description.

The intended consumer is a slide-building tool (Claude Design or similar): each
image can be viewed directly, and the matching `.txt` beside it says what the
figure shows, what the numbers on it are, why it is in the workshop, and how it
might be used on a slide.

```
figures/
  session1/   18 figures, from notebooks/session1_instructor.ipynb
  session2/   10 figures, from notebooks/session2_instructor.ipynb
```

Each figure is a pair sharing one basename:

```
session1/02-barbell-fiedler-vector-bottleneck.png    the image
session1/02-barbell-fiedler-vector-bottleneck.txt    the description
```

Filenames are numbered in notebook order, so sorting a directory gives the
narrative sequence of the session.

Each `.txt` has the same five sections: `TITLE`, `SOURCE` (notebook, cell,
workshop section and clock time), `WHAT IT SHOWS` (layout, panels, axes,
colours), `NUMBERS ON THE FIGURE`, `WHY IT IS HERE` (the teaching point), and
`SLIDESHOW NOTES` (suggested slide title, a one-line caption, the aspect ratio,
and where the figure belongs in a sequence).

## Session 1 — Graphs, Laplacians, and where the eigenvectors go

| # | Figure | In one line |
|---|--------|-------------|
| 01 | `spring-chain-normal-modes` | Six normal modes of a free-free spring chain; the k-th changes sign k times |
| 02 | `barbell-fiedler-vector-bottleneck` | The Fiedler vector splits a barbell graph exactly at its bridge |
| 03 | `ratiocut-vs-ncut-pendant-graph` | One pendant node hijacks RatioCut; Ncut is immune |
| 04 | `two-moons-kmeans-failure` | k-means can only draw straight boundaries, and the moons are not straight |
| 05 | `spectral-embedding-two-moons` | In eigenvector coordinates the moons collapse to two separable blobs |
| 06 | `spectral-clustering-affinity-comparison` | kNN vs RBF affinity: the graph you build is the model |
| 07 | `eigengap-plot` | Choosing k from the spectrum — a soft heuristic, shown honestly |
| 08 | `louvain-vs-planted-communities-confusion` | Louvain recovers both planted blocks and splits the ambiguous one 10/10 |
| 09 | `dublin-eds-third-level-education-choropleth` | The real dataset: 162 Dublin EDs by third-level education |
| 10 | `queen-vs-rook-contiguity-graphs` | Two defensible ways to turn one map into a graph (462 vs 414 edges) |
| 11 | `contiguity-graph-over-dublin-map` | The pivot slide: the map and the graph are the same object |
| 12 | `betweenness-centrality-map` | Which EDs are the bridges — and the source for Session 2's shock |
| 13 | `fiedler-vector-geometry-only-map` | Cutting Dublin in half using adjacency alone, no census data |
| 14 | `rathmines-ranelagh-street-network` | Optional cameo: a street network is a graph too |
| 15 | `edge-attribute-difference-histogram` | Where sigma comes from — the distribution of edge differences |
| 16 | `weighted-fiedler-median-sigma-map` | Weight edges by similarity and the boundary becomes meaningful |
| 17 | `sigma-sweep-three-panels` | Sigma is the model: too large gives geography, too small collapses lambda_2 |
| 18 | `unweighted-weighted-kmeans-cluster-comparison` | Geometry, attribute, or both — three ways to draw one line |

## Session 2 — Spatial autocorrelation, diffusion, and a capstone

| # | Figure | In one line |
|---|--------|-------------|
| 01 | `morans-i-permutation-histogram` | The observed Moran's I sits far outside 999 permutations of itself |
| 02 | `moran-scatterplot` | Moran's I is a regression slope, and its quadrants are the LISA types |
| 03 | `lisa-cluster-map` | Where the clustering is: HH in the south, LL in the north |
| 04 | `lisa-bh-corrected-vs-session1-clusters` | Correcting for 162 tests — and the agreement with Session 1 |
| 05 | `diffusion-snapshots-five-times` | A shock spreads from the busiest ED; the south-west stays dark |
| 06 | `modal-amplitude-decay` | Every mode decays except lambda_1, and lambda_2 decays slowest |
| 07 | `explicit-euler-stability-threshold` | 1% over dt = 2/lambda_max and explicit Euler diverges exponentially |
| 08 | `diffusion-with-fiedler-boundary` | The heat front stalls exactly on the spectral boundary |
| 09 | `capstone-leakage-vs-null-distributions` | Both boundaries beat all 1999 contiguous null draws — rank 0 |
| 10 | `shuffled-attribute-geography-destroyed` | Shuffle the values: Moran's I collapses, the clustering answers anyway |

## Suggested slideshow arc

The numbering already is the arc. Session 1 runs abstract to concrete —
springs, then graphs, then two moons, then Dublin — and Session 2 runs
inference, then dynamics, then the capstone that joins them.

Three figures carry the most weight and deserve room:

- `session1/02` — the Fiedler vector finding a bottleneck unprompted
- `session1/17` — the sigma sweep, the cautionary slide of the workshop
- `session2/08` — the diffusion front stopping on the spectral boundary

Four are marked cut-first in the instructor notes and can be dropped without
breaking anything: `session1/07`, `session1/14` (also requires `osmnx`),
`session2/02` and `session2/08`.

## Regenerating

The PNGs are extracted from the outputs already stored in the instructor
notebooks — nothing is re-run, so what is here is exactly what the notebooks
last produced.

```bash
python graph-workshop/figures/extract_figures.py
```

Run it from the repository root. It overwrites the PNGs in place and leaves the
`.txt` descriptions alone, so if a notebook is re-executed and a figure changes
materially, update the matching description by hand.
