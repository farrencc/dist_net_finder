# Graph-Based Computational Techniques

A one-day workshop in two 2.5-hour sessions. The slides carry the exposition; these
notebooks are what the room runs alongside them.

Everything is built on one object, the graph Laplacian `L = D - A`. It arrives in the
first half hour of Session 1 and every later topic — cuts, clustering, community
detection, spatial autocorrelation, diffusion — is another thing you do with it. One
graph, the 162 Electoral Divisions of Dublin City, survives from 1:45 in Session 1 to
the end of Session 2.

## Layout

```
graph-workshop/
  README.md
  environment.yml
  requirements.txt
  data/
    prepare_data.py           run once by the instructor, needs a network
    dublin_eds.gpkg           committed
    streets.graphml           committed
  notebooks/
    session1.ipynb            student
    session2.ipynb            student
    session1_instructor.ipynb student file + tuning notes, cut-first markers, solution
    session2_instructor.ipynb
```

The instructor files are separate notebooks, not the student files behind a flag, so the
two can be edited without stepping on each other.

## Running it

Locally:

```
conda env create -f environment.yml     # or: pip install -r requirements.txt
conda activate graph-workshop
jupyter lab notebooks/session1.ipynb
```

On Colab: open the notebook from GitHub. The first cell detects Colab, installs the
spatial stack and pulls the two data files from `REPO_RAW`. On a local machine that cell
does nothing and prints nothing.

`REPO_RAW` at the top of each notebook points at `main`. If the workshop is served from a
branch or a fork, change it there.

**Neither notebook touches the network during the workshop.** Both run end to end with
networking disabled, given the two committed data files. Only `prepare_data.py` needs a
connection, and only once, in advance.

## The data

`dublin_eds.gpkg` — the 162 Electoral Divisions of Dublin City, CSO 2022 boundaries
generalised to 20 m, reprojected to EPSG:2157 (Irish Transverse Mercator). Latitude and
longitude are angles: centroids and distances taken in EPSG:4326 would be quietly wrong,
so the file is stored already projected.

One census attribute is attached: `pct_third_level`, the share of persons aged 15 and over
whose highest completed education is Higher Certificate or above, from SAPS 2022 table
T10_4, joined on `ED_GUID`. It runs 9.2 % to 85.6 %, skew −0.03 — symmetric enough that no
log transform is needed, which keeps Session 1 section 7 honest — and Moran's I on it is
+0.71, so there is real spatial structure for the Moran and clustering blocks to find.

Queen contiguity gives 462 edges, mean degree 5.70, and the graph is connected. That last
point is load-bearing: a disconnected contiguity graph makes λ₂ zero and silently breaks
the Fiedler, diffusion and Moran blocks downstream. `prepare_data.py` checks it and stops
with component sizes rather than quietly taking the largest component.

`streets.graphml` — the drive network of Rathmines and Ranelagh, 414 nodes and 909 edges,
from OpenStreetMap via Overpass. Two parallel radials into the same canal bridges with
side streets joining them: a district with genuine route choice, which the Braess block
needs and a uniform grid would not give.

To rebuild either file:

```
cd data && python prepare_data.py
```

It prints the national ED count, the Dublin City count, the CRS before and after
reprojection, the attribute's range and skew, the node and edge counts, connectivity and
the street network size. Overpass rate-limits aggressively; the street fetch retries with
backoff.

## Session 1

| | | |
|---|---|---|
| 0:00 | 1 | Hook |
| 0:10 | 2 | Eigenvector refresher — free-free spring chain, `eigh`, sign and degeneracy hygiene |
| 0:20 | 3 | Laplacian — `D - A`, the incidence matrix, the quadratic form, Fiedler, λ₂ |
| 0:50 | 4 | Spectral clustering — MinCut vs RatioCut vs Ncut, two moons, the eigengap |
| 1:20 | 5 | Community detection — Louvain on a planted partition |
| 1:45 | 6 | Geospatial — the Dublin graph, betweenness, the Fiedler map |
| 2:05 | 7 | Applied: weighted clustering |
| 2:15 | 8 | Braess (appendix, read afterwards) |

Students type nothing until section 7. Section 7 has exactly one knob, `SIGMA`, isolated
in its own cell.

## Session 2

| | | |
|---|---|---|
| 0:00 | 1 | Recap |
| 0:10 | 2 | Moran's I — permutation inference, LISA, multiple comparisons |
| 0:45 | 3 | Diffusion — `du/dt = -Lu`, modal decay, Euler's stability threshold |
| 1:35 | 4 | Capstone |
| 2:15 | 5 | Wrap-up |

Session 2 reloads `data/session1_state.npz`, written by Session 1 section 7. If a student
arrives without it — a fresh Colab runtime, a different machine — section 0 recomputes the
two label vectors from the committed `.gpkg` and says so. Nothing else changes.

The capstone is individual work. `session2.ipynb` contains the starter functions and four
hints and stops there; the worked solution, with the measured margin against the
contiguous null, is in `session2_instructor.ipynb`.
