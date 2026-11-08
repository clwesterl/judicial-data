# Courts of appeals seats

Read this for any question about judgeship succession — who held a seat, who
replaced whom, how a circuit's composition changed as seats turned over.

## What a seat is

A **seat** is an authorized judgeship, not a judge and not a chair in a
courtroom. Congress creates judgeships by statute; a judge occupies one until
death, resignation, elevation, or **senior status**; then a successor is
appointed to the same judgeship. The chain of occupants of one judgeship is what
this dataset tracks.

This matters because the usual judge-level panel cannot answer "what happened to
*this* seat when Souter left for the Supreme Court" — it has no notion of the
seat. Seat-level data turns a circuit into a fixed set of slots whose occupants,
and so whose ideology, change at identifiable moments.

## Seats are looked up, not inferred

The FJC's Federal Judicial Service export assigns every appointment an official
**`Seat ID`** and, for the first occupant of a new judgeship, the **statute that
created it**. The ID encodes circuit, seat, and occupancy sequence:

```
CA1 01 03      First Circuit, seat 1, third occupant
CADC 01 02     D.C. Circuit, seat 1, second occupant
CAFC 02 01     Federal Circuit, seat 2, first occupant
```

So succession is read off the data rather than reconstructed. That is worth
stating plainly because the obvious alternative — inferring chains from
confirmation and departure years, preferring a vacant seat last held by a judge
from the appointee's own state — gets real cases wrong. On the First Circuit that
approach put **Breyer** in Mahoney's seat when he actually filled a *new* 1978
Omnibus Judgeship Act seat (92 Stat. 1629), and merged Woodbury and Coffin into
one chain when they held seats 2 and 3. The failure is structural: a long gap
between occupants is ambiguous between "the seat sat vacant" and "this judgeship
did not exist yet," and nothing in a judge-level file resolves it. The FJC's
creating-statute field resolves it directly.

Ten appointments carry a `Seat ID` ending **`SR`** rather than a number: six
senior judges reassigned to the Eleventh Circuit at the 1981 split (94 Stat.
1994) and four to the Federal Circuit in 1982 (96 Stat. 25). They held no
authorized judgeship, so they have no seat and are excluded.

## Occupancy ends at senior status

A judge who takes senior status keeps hearing cases but **vacates the
judgeship**, which is what allows a successor to be appointed. So occupancy runs
from the commission date to whichever comes first of senior status or
termination. This is the single choice that makes the data reconcile to statute —
scoring occupancy to death or retirement instead would double-count seats for
decades at a time.

Consequence: a judge appears in this panel for a shorter span than their service
record shows. For active-plus-senior service, use the CCAD panel data, where
senior judges still sit.

## Validation

**Occupied seats in 2025 equal the authorized judgeships in all thirteen
circuits — 179 against 179.**

| circuit | seats ever | 2025 | 28 U.S.C. §44 |
|---|---|---|---|
| First | 6 | 6 | 6 |
| Second | 15 | 13 | 13 |
| Third | 15 | 14 | 14 |
| Fourth | 16 | 15 | 15 |
| Fifth | 29 | 17 | 17 |
| Sixth | 17 | 16 | 16 |
| Seventh | 12 | 11 | 11 |
| Eighth | 14 | 11 | 11 |
| Ninth | 30 | 29 | 29 |
| Tenth | 12 | 12 | 12 |
| Eleventh | 12 | 12 | 12 |
| D.C. | 13 | 11 | 11 |
| Federal | 12 | 12 | 12 |

"Seats ever" exceeds today's authorization where judgeships were transferred or
reallocated. The Fifth shows 29 against 17 — exactly the **12** judgeships that
went to the Eleventh in 1981, which is an independent check on the split
accounting. The Eighth's extra 3 trace to the creation of the Tenth Circuit.

Occupancy over time tracks the statutory growth: 28 seats in 1900, 43 in 1930,
65 in 1950, 67 in 1960, 96 in 1970, 129 in 1980, 164 in 1990, 179 today.

## Contents

| table | rows | one row per |
|---|---|---|
| `seats()` | 203 | seat: creating statute, span, occupant count, filled now |
| `seats("spells")` | 868 | occupancy: predecessor, ideology shift, vacancy length, why they left |
| `seat_panel()` | 12,565 | seat-year: occupant, ideology, appointing president — **derived**, not stored |

A vacant seat-year is simply absent from the panel, so a gap is a vacancy. Spells
on a seat never overlap: an occupancy is closed at the next occupant's arrival
when a departure and an appointment fall in the same year.

## Using it

```python
import scdb
scdb.seats()                      # 203 judgeships
scdb.seats("spells")              # 868 occupancies
scdb.seat_panel(1950, 2026)       # circuit x seat x year, derived from the spells
scdb.find_judge("reinhardt")      # a judge's seats, the CoA analogue of justice()
scdb.seat_history(1, 3)           # everyone who has held First Circuit seat 3
scdb.court_composition(9, 1995)   # who sat on the Ninth in 1995
```

```r
source("scripts/scdb.R")
scdb_seats(); scdb_seats("spells")
scdb_seat_panel(1950); scdb_seat_history(1, 3); scdb_court_composition(9, 1995)
```

The year panel is **derived, not stored**, so it cannot drift away from the
spells. A vacant seat-year is simply absent from it, so a gap in a seat's rows
is a real vacancy.

## Ideology is a step function that sometimes doesn't step

JCS scores join from the skill's own `jcs("coa")` table and are
**appointment-based and time-invariant** — one score per judge for their whole career. So a seat's
ideology changes only at turnover, and not always then: two judges appointed by
the same president from the same state score identically. On the First Circuit,
Thompson → Montecalvo shows a shift of exactly 0.000. Thirty transitions in the
dataset are flat for this reason. Occupancy is the reliable signal; treat
`jcs_shift` as informative about direction, not magnitude, and do not read a
zero as "no change in the seat."

Coverage runs out in the early decades: the JCS appeals-judge table starts in
the 1920s, so appointments before roughly 1939 carry no score at all, and the
most recent appointees have none yet. The `jcs_match` column records how each
join was made, or why it failed, so that era can be filtered rather than
silently averaged over.

Name matching is non-trivial and documented in `scripts/matchjcs.py`. The two
sources disagree on accents (`Gelpí`), on two-word surnames (`Coney Barrett,
Amy` against `Barrett, Amy Coney`) and on judges who go by a middle name
(`Duncan, Kyle` against `Duncan, Stuart Kyle`), so a candidate must share a
surname token, share a given-name token (an initial standing for the name it
abbreviates) and sit on the same circuit, and is accepted only when exactly one
judge qualifies. The loose given-name rule ties exactly one pair together in
705 judges — **Morris S. and Richard S. Arnold**, brothers who both sat on the
Eighth Circuit and share a middle initial — and that tie breaks on the first
given name, separating them correctly. Zero ambiguous matches remain.

The bundled table carries no home state, so `state` is empty unless the build
is given a research master that has one. Since circuit judgeships are
informally state-tied, that is a real gap for seat-level work; pass `--master`
when you have such a file.

## Rebuilding it

Both inputs live in the repo — the FJC export under `fjc-raw/`, the scores in
`data/jcs/` — so the build needs nothing local:

```bash
python scripts/build_seats.py --fjc fjc-raw/federal-judicial-service.csv.gz \
                              --out data/coa
```

Add `--master <file.dta>` to score from a research master instead of the
bundled table; that is also the only way to populate home states.

To refresh the FJC export (fjc.gov blocks automated clients, so fetch it in a
browser or from your own machine):

```bash
curl -LO https://www.fjc.gov/sites/default/files/history/federal-judicial-service.csv
gzip -9 -c federal-judicial-service.csv > fjc-raw/federal-judicial-service.csv.gz
```
or use the download links at
<https://www.fjc.gov/history/judges/biographical-directory-article-iii-federal-judges-export>.

The build prints the validation table above; if the 2025 column stops matching
§44, either the FJC release changed its Seat ID scheme or `STATUTORY` in
`build_seats.py` needs updating for a new judgeship act.

A research master, if supplied, must have `name`, `circuit` (1–11, 12 = D.C.,
13 = Federal), `YearConfirm`, `jcs_2024` and `state_abbrev`. Rows with no
circuit are treated as Supreme Court justices and dropped; `state_abbrev ==
"ZUSA"` means no home state, which is correct for the D.C. and Federal
Circuits. Verified against the bundled table on the First Circuit: 25 of 25
judges matched with every score identical, and the same 12 occupancies unscored
either way.

## Cross-references

Circuit numbering here follows the JCS scheme (12 = D.C., 13 = Federal), **not**
the CCAD's (0 = D.C., 12 = Federal). `jcs("circuits")` carries both — see
`coa.md`, which also covers the CCAD case data and the SCDB crosswalk.
