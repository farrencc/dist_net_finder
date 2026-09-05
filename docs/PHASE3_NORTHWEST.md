# Phase 3: the North-West subnetwork, and the 15-node dataset

`northwest.py` extracts the North West — EirGrid's Wind Dispatch Tool
constraint groups 1–3 — from a TYTFS case, in two views, and reconciles it
against a hand-built 15-node dataset. `test_northwest.py` guards it.

```bash
python northwest.py circuits     # the circuit table, both views
python northwest.py balance      # capacity, dispatch, demand, boundary flow
python northwest.py extract      # -> data/pypsa/northwest_<case>_<view>/
python northwest.py verify       # connectivity, DC PF, LOPF, agreement
python northwest.py windy        # the region with its wind running
```

> **What this was reconciled against.** `nodes.xlsx` is not in this repository
> and was not reachable from the session that wrote this, and neither was the
> Part 3 circuit table. Everything below is derived from TYTFS alone; the
> hand-built dataset enters only through the four figures quoted in the brief
> — 15 nodes, 16 circuits, ~425 MW of supply capacity, ~160 MW of demand — and
> through the five stations named as folded. **The station set in §1 is
> therefore an inference, not a copy**, and §3 says exactly what it was
> inferred from. Give me the file and I will diff it properly; nothing below
> depends on it being right except the identity of the three southern
> stations.

---

## 1. The region

Named, not derived. A constraint group is a published grouping, and — see §5 —
the North West is *not* the radial island behind Srananagh that a purely
topological definition would find, so there is nothing to derive it from.
Every bus is listed in `northwest.py` so that what is in and what is out can
be read rather than inferred.

### The aggregated view — 15 stations

| station | kV | TYTFS buses | folds in |
|---|---|---|---|
| Ardnagappary | 110 | 1571 | |
| Binbane | 110 | 1341 | |
| Cathaleen's Fall | 110 | 1701, 1761, 17010, 17061 | **Cliff** |
| Clogher | 110 | 2801, 2870, 2871, 4091, 28019, 28710, 28712 | **Golagh**, **Mulreavy** |
| Corderry | 110 | 1631 | |
| Corraclassy | 110 | 1981 | |
| Croaghonagh | 110 | 51911 | |
| Drumkeen | 110 | 2321, 4071 | **Meentycat** |
| Letterkenny | 110 | 3581, 3591, 35861, 35862 | **Lenalea** |
| Sligo | 110 | 4981, 49861 | |
| Sorne Hill | 110 | 4991 | |
| Srananagh 110 | 110 | 5041 | |
| Srananagh 220 | 220 | 5042 | |
| Tievebrack | 110 | 5191 | |
| Trillick | 110 | 5361 | |

### The native view — 20 stations

The same region with the five folded stations standing on their own, which is
how TYTFS has them: **Cliff** (1761), **Golagh** (2801 and the tee point
28019), **Mulreavy** (4091), **Meentycat** (4071), **Lenalea** (3591).

Within a station, TYTFS's own busbars are joined by zero-impedance couplers
and are one place. Clogher is four 110 kV busbars, Cathaleen's Fall three
(two busbars and a capacitor), Letterkenny three (busbar, capacitor, SVC),
Sligo two. Merging them is exact to the fourth decimal place, and it is what
makes the aggregated view expressible at all.

---

## 2. The circuit table, and where I disagree

**I agree there are 16 — if 16 counts routes. TYTFS has 19 circuits on those
16 routes.**

A hand-built node-and-edge list has one edge per pair of stations that are
joined. A PSS/E case has one record per circuit, and **three of the region's
routes are double circuits**. That is the whole of the disagreement, and it is
a counting convention rather than a difference about the network.

### The 15-station view: 16 routes, 19 circuits

| route | ckt | from bus | to bus | km | RATE1 (MVA) | |
|---|---|---|---|---|---|---|
| Ardnagappary – Tievebrack | 1 | 1571 ARDNAGAPPARY | 5191 TIEVEBRACK | 35.00 | 91 | |
| Binbane – Cathaleen's Fall | 1 | 1341 BINBANE | 1701 CATH_FALL | 34.30 | 210 | |
| Binbane – Tievebrack | 1 | 1341 BINBANE | 5191 TIEVEBRACK | 23.20 | 159 | |
| Cathaleen's Fall – Clogher | 1 | 2870 CLOGHER | 17010 CATH FALL | 26.07 | 209 | **double** |
| Cathaleen's Fall – Clogher | 2 | 1701 CATH_FALL | 28712 CLOGHER | 25.74 | 210 | **double** |
| Cathaleen's Fall – Corraclassy | 1 | 1701 CATH_FALL | 1981 CORRACLASSY | 61.30 | 210 | |
| Cathaleen's Fall – Srananagh 110 | 1 | 1701 CATH_FALL | 5041 SRANANAGH | 52.63 | 191 | **double** |
| Cathaleen's Fall – Srananagh 110 | 2 | 5041 SRANANAGH | 17010 CATH FALL | 49.67 | 210 | **double** |
| Clogher – Croaghonagh | 1 | 28710 CLOGHER | 51911 CROAGHONAGH | 9.61 | 183 | |
| Clogher – Drumkeen | 1 | 2321 DRUMKEEN | 28710 CLOGHER | 27.00 | 123 | |
| Clogher – Letterkenny | 1 | 3581 LETTERKENNY | 28019 GOLAGH T | 38.40 | 121 | via the Golagh tee |
| Corderry – Srananagh 110 | 1 | 1631 CORDERRY | 5041 SRANANAGH | 12.70 | 210 | |
| Drumkeen – Letterkenny | 1 | 2321 DRUMKEEN | 3581 LETTERKENNY | 8.35 | 123 | |
| Letterkenny – Tievebrack | 1 | 3591 LENALEA | 5191 TIEVEBRACK | 33.13 | 159 | **through folded Lenalea** |
| Letterkenny – Trillick | 1 | 3581 LETTERKENNY | 5361 TRILLICK | 34.05 | 123 | |
| Sligo – Srananagh 110 | 1 | 4981 SLIGO | 5041 SRANANAGH | 10.77 | 121 | **double** |
| Sligo – Srananagh 110 | 2 | 4981 SLIGO | 5041 SRANANAGH | 11.19 | 121 | **double** |
| Sorne Hill – Trillick | 1 | 4991 SORNE HILL | 5361 TRILLICK | 4.40 | 123 | |
| Srananagh 110 – Srananagh 220 | 1 | 5042 SRANANAGH | 5041 SRANANAGH | — | 250 | transformer |

16 routes. 19 circuits — 18 lines and one transformer.

### The 20-station view: 21 routes, 24 circuits

Unfolding the five adds five routes — Cathaleen's Fall–Cliff,
Clogher–Golagh, Clogher–Mulreavy, Drumkeen–Meentycat, Lenalea–Letterkenny —
and splits Letterkenny–Tievebrack back into Lenalea–Tievebrack. 23 lines and
the transformer.

### Two things in that table worth knowing

**Cathaleen's Fall–Clogher and Cathaleen's Fall–Srananagh are double circuits
that land on different busbars.** Circuit 1 of the Clogher pair runs
2870 → 17010; circuit 2 runs 1701 → 28712. Treating Cathaleen's Fall as one
node and Clogher as one node is what makes them parallel; in the case they are
not, quite. The same is true of the Srananagh pair. This is why the two views
have to be built from bus numbers rather than from station names.

**Clogher–Letterkenny goes through the Golagh tee.** Bus 28019 GOLAGH T is a
tee point on the Letterkenny–Clogher line with Golagh's own station hanging
off it. In the native view that is two circuits (Letterkenny–Golagh T and
Golagh T–Clogher plus Golagh–Golagh T); in the aggregated view Golagh folds
into Clogher and it is one.

---

## 3. How the station set was inferred, and how confident I am

The five folded stations were given. The 12 stations they imply — the ten
Donegal stations plus Srananagh's two busbars — produce **15 circuits on 13
routes**, which is neither of the target numbers. Adding stations one at a
time and counting:

| stations added | stations | circuits | routes |
|---|---|---|---|
| — (Donegal + Srananagh) | 12 | 15 | 13 |
| + Corraclassy | 13 | 16 | 14 |
| + Corraclassy, Corderry | 14 | 17 | 15 |
| **+ Corraclassy, Corderry, Sligo** | **15** | **19** | **16** |

Only one 15-station set in the neighbourhood gives 16 of anything, and it
gives 16 routes. Corraclassy, Corderry and Sligo are also the three stations
directly adjacent to the region — Corraclassy on Cathaleen's Fall, Corderry
and Sligo on Srananagh 110 — so they are what a hand-built dataset would draw
its boundary around anyway.

**Confidence: high on the 12 Donegal stations and Srananagh, moderate on
Corraclassy / Corderry / Sligo.** Nothing else in this document depends on the
southern three: remove them and the counts change, the boundary moves out one
station, and every other conclusion stands.

---

## 4. Cathaleen's Fall and Clady

**Cathaleen's Fall is in TYTFS**, under a name the twelve-character field
cannot hold. It is three buses:

| bus | name | what |
|---|---|---|
| 1701 | `CATH_FALL` | 110 kV busbar |
| 17010 | `CATH FALL` | the other 110 kV busbar, joined by a zero-impedance coupler |
| 17061 | `CATH_CAP` | the station capacitor, on another coupler |

with the machines below it at 10.5 kV (`HY_CATHG3`, `HY_CATHG4`, 22.5 + 23.0
MVA, both in service in WP2024) and 17.0 MW of 38 kV demand on
`HY_CATH FALL`. In OpenStreetMap it is *Cathleen's Fall 110kV Substation* —
spelled without the second 'a' — at 54.4988 N, 8.1770 W, which is how
`geocode.py` places it, through its alias table.

**Cliff**, the Erne's other station, is bus 1761, 5.5 km away, with two 10 MW
units. The hand-built dataset folds it into Cathaleen's Fall; TYTFS does not.

**Clady is not in TYTFS at any voltage, and that is not a naming problem.**
Three independent sources agree on what it is:

- **OpenStreetMap** has *Clady 38kV Substation* (ESB Networks) and *Clady
  Hydroelectric Station* (ESB Generation), both at 55.0381 N, 8.2717 W in
  Gweedore, Co. Donegal, both tagged **38 kV**.
- **EirGrid's own asset register**, the 161-station 110 kV-and-above layer in
  `data/eirgrid_transmission.gpkg`, does not contain it.
- **TYTFS** has no bus whose name contains `CLAD`, at 380, 275, 220, 110, 38,
  20, 10 kV or anywhere else.

A 38 kV ESB Networks station is below the transmission model's floor. TYTFS
carries the sub-110 kV network only as the stub that load and small generation
hangs off, and Clady's 4.2 MW does not earn a bus of its own.

**Where it would be if it were there.** The nearest transmission station is
**Ardnagappary** (bus 1571), 2.0 km north at 55.0565 N, 8.2692 W. What
Ardnagappary actually carries is 9.67 MW of 38 kV demand and the **Cronalaght**
wind farm — three records, 22.94 MVA, all out of service in WP2024 — and **no
hydro unit at all**. So if `nodes.xlsx` has a Clady node with generation on
it, that generation is not in TYTFS, at Ardnagappary or anywhere else.

*One near-miss, ruled out.* `HY_GLENTIES` (bus 13434, 38 kV under Binbane)
carries a 4.3 MW in-service machine, which is within 0.1 MW of Clady's rating.
It is not Clady: it sits 7.4 km from Binbane's 38 kV busbar, in the Glenties
area, roughly 30 km from Gweedore. The coincidence is a coincidence. (While
checking it: the `HY_` prefix in these files is **not** "hydro" — it prefixes
38 kV load busbars too, including `HY_CARLOW`, `HY_NAVAN` and `HY_WATERFORD`,
434.7 MW of demand between the eleven of them. Phase 2's carrier inference
reads it only on generator buses, where it does mean hydro, so that inference
is unaffected.)

---

## 5. Srananagh, and the thing the hand-built model gets wrong

Srananagh is bus 5041 at 110 kV and bus 5042 at 220 kV, as stated. The
extraction slacks at the 220 kV busbar, as asked. Two corrections to the
premise, both of which matter for what the model is used for.

### The transformer is three-winding, and there is only one of it

```
5042 SRANANAGH 220 kV  --+
                          +-- 250 MVA, X = 0.064 pu on 100 MVA
5041 SRANANAGH 110 kV  --+
                          +-- 50421 SRANANAGH 10.5 kV, tertiary,
                              no generator and no load
```

One 250 MVA unit, with an idle 10.5 kV tertiary. `pypsa_net.py` splits
three-winding transformers into a star; here the extraction keeps the 220/110
leg as a single two-winding transformer, which is exact because nothing hangs
on the tertiary.

### The region is not radial behind Srananagh

Removing that transformer leaves **every** North-West bus still connected to
the 220 kV network. There are **eight** boundary ties, not one:

| from | to | kV | ckt | km | RATE1 | flow into the region, WP2024 |
|---|---|---|---|---|---|---|
| Srananagh 220 | FLAGFORD 220 | 220 | 1 | 56.0 | 513 | **+92.9 MW** |
| Sligo | FLAGFORD | 110 | 1 | 50.5 | 121 | +24.4 MW |
| Corderry | ARIGNA_T | 110 | 1 | 13.7 | 210 | +17.9 MW |
| Corraclassy | ENNK_PST (Enniskillen, NI) | 110 | 1 | 27.5 | 121 | +5.5 MW |
| Corraclassy | GORTAWEE | 110 | 1 | 10.9 | 210 | +2.6 MW |
| Corderry | GARVAGH | 110 | 1 | 5.8 | 210 | 0.0 MW |
| Sligo | CUNGHILL | 110 | 1 | 21.1 | 210 | −6.4 MW |
| Letterkenny | STRA_PST (Strabane, NI) | 110 | 1 | 22.3 | 93 | −20.5 MW |

Two of them cross into Northern Ireland. A 15-node model that stops at
Srananagh is modelling one of eight doors, and §7 shows that under load it is
not even the widest one.

---

## 6. Supply, demand and the export claim

### The hand-built figures against TYTFS

| | hand-built | TYTFS WP2024 | |
|---|---|---|---|
| supply capacity | ~425 MW | **771.1 MW** | +81% |
| demand | ~160 MW | **185.8 MW** | +16% |
| ratio | 2.7 : 1 | **4.2 : 1** | |

**The demand agrees to within about 16%**, which for a peak-demand figure from
two different vintages is agreement. **The capacity does not, and the
direction is the interesting part**: TYTFS has 81% more connected capacity in
the region than the hand-built dataset does. That is the Donegal wind
build-out. The region is *more* export-dominated in TYTFS 2024 than in the
hand-built data, not less.

Station by station, WP2024, aggregated view:

| station | machines | capacity MW | dispatched MW | demand MW |
|---|---|---|---|---|
| Croaghonagh | 2 | 139.2 | 0.0 | — |
| Clogher (+Golagh, +Mulreavy) | 6 | 110.3 | 0.0 | — |
| Drumkeen (+Meentycat) | 3 | 85.0 | 0.0 | — |
| Cathaleen's Fall (+Cliff) | 5 | 83.0 | 65.0 | 17.0 |
| Binbane | 14 | 75.1 | 4.3 | 18.7 |
| Letterkenny (+Lenalea) | 7 | 70.8 | 0.0 | 66.1 |
| Corderry | 11 | 63.3 | 0.0 | — |
| Sorne Hill | 10 | 63.3 | 0.0 | — |
| Trillick | 6 | 44.7 | 0.0 | 20.1 |
| Ardnagappary | 3 | 22.9 | 0.0 | 9.7 |
| Sligo | 2 | 13.7 | 0.0 | 54.2 |
| Corraclassy, Croaghonagh, Srananagh ×2, Tievebrack | — | — | — | — |
| **total** | **69** | **771.1** | **69.3** | **185.8** |

### The boundary flows do *not* show export, and that is not a contradiction

| case | capacity | dispatched | demand | net into the region | via Srananagh 220 | machines running |
|---|---|---|---|---|---|---|
| WP2024 | 771.1 | 69.3 | 185.8 | **+116.5** | +92.9 | 5 of 69 |
| SV2024 | 723.1 | 0.0 | 59.7 | **+59.7** | +35.8 | 0 |
| WP2033 | 945.4 | 152.3 | 208.7 | **+56.4** | +43.3 | 76 of 94 |
| SV2033 | 945.4 | 40.0 | 59.5 | **+19.5** | +29.0 | 2 |

**In all four published cases the North West imports.** Not slightly — it
imports its whole demand less a little hydro. The reason is the one Phase 1
found in a different guise: these are security cases with `STAT` doing the
work. The winter-peak cases run 5 of the region's 69 machines and the summer
cases run none, because a peak-security study does not credit wind. 69.3 MW of
772 MW is a 9% dispatch.

So the answer to "confirm the TYTFS boundary flows are consistent with export
dominance" is: **they are not, and they cannot be, because none of the four
published cases is a high-wind case.** The export the Wind Dispatch Tool
exists to manage does not appear in any of them. The capacity that causes it
does — and TYTFS has 81% more of it than the hand-built dataset.

---

## 7. What happens when the wind blows

`python northwest.py windy --capacity-factor X` puts the region's connected
capacity to work at *X* of `PT` and re-solves. It runs on the **whole**
transmission network, not on the extract: the region has eight ties, and an
extract that holds seven of them where the case put them sends every extra
megawatt out through Srananagh and produces an answer that is both large and
meaningless.

It is a what-if and not a case. Nothing outside the region is re-dispatched,
so it says where the region's power would *try* to go, not what the system
would do about it.

| capacity factor | net export | worst boundary tie | Srananagh 220 |
|---|---|---|---|
| 20% | −31 MW (still importing) | Letterkenny–Strabane 0.63× | +78 MW in |
| 30% | 46 MW | Letterkenny–Strabane 0.94× | +63 MW in |
| **40%** | **123 MW** | **Letterkenny–Strabane 1.24×** | +48 MW in |
| 60% | 277 MW | Letterkenny–Strabane 1.86× | +18 MW in |
| 100% | 585 MW | Letterkenny–Strabane 3.09× | 42 MW out |

**The binding constraint is the Letterkenny–Strabane 110 kV tie into Northern
Ireland, 93 MVA, and it binds at about 32% of connected capacity.** Srananagh
220 is barely loaded at any of these — it is still importing at 80% capacity
factor and never carries more than 42 MW out against a 513 MVA circuit and a
250 MVA transformer. The region's *internal* circuits reach 0.99× at full
output; the constraint is at the boundary, not inside.

That is a direct disagreement with the premise that Srananagh 220 is the
region's export path. In a DC flow with the rest of the system held still, it
is not: the 110 kV ties north-east into Northern Ireland and south into
Flagford take most of the surplus. Two caveats, both real: nothing outside the
region is re-dispatched, and the system's reference bus is Turlough Hill,
far away. A study that cares about the answer should redo it with the NI
network dispatched rather than fixed.

Srananagh remains the right place to **slack** the extraction, because it is
where the region's own model ends. It is not where the power goes.

---

## 8. The two extractions, and what the 15-node topology costs

`python northwest.py extract` writes both views to
`data/pypsa/northwest_<case>_<view>/`, as PyPSA CSV folders with the same
schema Phase 2 uses, plus `reports/`:

| file | what |
|---|---|
| `stations.csv` | the station set, its buses, and what folds into it |
| `circuits.csv` | every circuit, with both endpoint buses and its impedance |
| `routes.csv` | the same collapsed to one row per station pair |
| `balance.csv` | capacity, dispatch and demand per station |
| `boundary.csv` | the eight ties and the MW on each |
| `agreement_with_full.csv` | the extract's flows against the full network's |

Every boundary tie but Srananagh is pinned at the MW the full network's DC
solve puts on it — by its bounds and not only by `p_set`, so that it stays
pinned in an optimisation, where PyPSA releases `p_set`. Srananagh is left
free, because it is the reference and has to absorb whatever the region does
not.

### The verification that matters

Same impedances, same injections, a different reference bus: a DC flow has to
put the same MW on every circuit as the full network does.

| view | circuits | worst disagreement with the full network |
|---|---|---|
| native (20 stations) | 23 lines | **0.0099 MW** |
| aggregated (15 stations) | 18 lines | **1.74 MW** |

The native extraction is exact to a hundredth of a megawatt. The residual is
the zero-impedance couplers that were merged to make a station one bus, and
`X = 0.0001` pu is where it comes from.

**The aggregated view is not exact, and 1.74 MW is what the 15-node topology
costs.** Four of the five folds are radial spurs and cost nothing — Cliff,
Golagh, Mulreavy and Meentycat each have exactly one 110 kV neighbour, so
folding them moves an injection and removes a dead end. **Lenalea is not.** It
sits between Letterkenny and Tievebrack, so folding it into Letterkenny drops
the Letterkenny–Lenalea circuit and turns Lenalea–Tievebrack into a
Letterkenny–Tievebrack circuit that has lost 12.2 km of impedance. The three
circuits carrying the 1.74 MW error are all in that loop:
Binbane–Cathaleen's Fall, Binbane–Tievebrack, and the ex-Lenalea circuit
itself.

If the 15-node dataset is used for anything that cares about flows in the
Binbane–Tievebrack–Letterkenny triangle, that is the number to know. For
everything else the two views agree to well under a megawatt.

### Both solve

| case | view | connected | DC PF | LOPF (HiGHS) | max circuit loading |
|---|---|---|---|---|---|
| WP2024 | native | yes | solved | optimal | 0.38× |
| WP2024 | aggregated | yes | solved | optimal | 0.37× |

---

## 9. Summary of the discrepancies

| # | what | verdict |
|---|---|---|
| 1 | **16 circuits** | Agreed as **routes**; TYTFS has **19 circuits** on those 16 routes. Three routes are double circuits: Cathaleen's Fall–Clogher, Cathaleen's Fall–Srananagh, Sligo–Srananagh. |
| 2 | **15 nodes** | Reproduced, and the five folds are radial except Lenalea. The native view is 20. |
| 3 | **Cathaleen's Fall missing** | It is there, as `CATH_FALL` / `CATH FALL` / `CATH_CAP`. OSM spells it *Cathleen's*. |
| 4 | **Clady missing** | Genuinely absent, at every voltage. It is a 38 kV station, below the model's floor. If the hand-built node carries generation, TYTFS does not have it. |
| 5 | **Srananagh as the export path** | Right place to slack, wrong about the power. Eight boundary ties; Letterkenny–Strabane binds first, at ~32% capacity factor. |
| 6 | **~425 MW supply** | TYTFS has **771 MW** in the same 15 stations — 81% more. The wind build-out. |
| 7 | **~160 MW demand** | TYTFS has **186 MW** — agreement, for a peak figure of a different vintage. |
| 8 | **export-dominated** | True of the capacity, false of all four cases' flows: every one of them imports, because none dispatches the region's wind. |
| 9 | **the 15-node topology** | Costs up to **1.74 MW** of circuit flow, all of it around Lenalea. |

---

## 10. What is still open

- **`nodes.xlsx`.** The station set in §1 is inferred from the counts, not
  copied. The three southern stations — Corraclassy, Corderry, Sligo — are the
  part I would most like to check.
- **The constraint-group definition.** "Groups 1–3" is taken to mean the
  Donegal and north Connacht network; if EirGrid's published grouping differs,
  the region moves and §2's counts move with it. Changing it is one table in
  `northwest.py`.
- **§7 with the rest of the system dispatched.** The high-wind result holds
  everything outside the region fixed, which is why so much of the surplus
  goes to Northern Ireland. That is the next thing to do properly.
