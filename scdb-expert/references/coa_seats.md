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

| file | rows | one row per |
|---|---|---|
| `coa_seats.csv` | 203 | seat: creating statute, span, occupant count, filled now |
| `coa_seat_spells.csv` | 868 | occupancy: predecessor, ideology shift, vacancy length, why they left |
| `coa_seat_years.csv` | 12,565 | seat-year: occupant, ideology, appointing president |

A vacant seat-year is simply absent from the panel, so a gap is a vacancy. Spells
on a seat never overlap: an occupancy is closed at the next occupant's arrival
when a departure and an appointment fall in the same year.

## Ideology is a step function that sometimes doesn't step

JCS scores join from the judge master file and are **appointment-based and
time-invariant** — one score per judge for their whole career. So a seat's
ideology changes only at turnover, and not always then: two judges appointed by
the same president from the same state score identically. On the First Circuit,
Thompson → Montecalvo shows a shift of exactly 0.000. Thirty transitions in the
dataset are flat for this reason. Occupancy is the reliable signal; treat
`jcs_shift` as informative about direction, not magnitude, and do not read a
zero as "no change in the seat."

Coverage: 690 of 868 appointments (79.5%) carry a score — 95.9% for 1950–89 and
92.1% for 1990–2026, but only 31% before 1950, because the master file begins in
1924. The `jcs_match` column records how each join was made (or why it failed),
so the pre-1950 era can be filtered rather than silently averaged over. Name
matching is non-trivial and documented in `scripts/matchjcs.py`: the sources
disagree on accents (`Gelpí`), two-word surnames (`Coney Barrett, Amy` vs
`Barrett, Amy Coney`) and middle-name usage (`Duncan, Kyle` vs `Duncan, Stuart
Kyle`), so matching is on surname-token and given-name-token overlap guarded by
circuit and confirmation year, accepted only when exactly one master judge
qualifies. Zero ambiguous matches result.

The 26 post-1950 misses are mostly the Federal Circuit's 1982 founding cohort,
who transferred in from the Court of Claims and the CCPA rather than being
appointed to a circuit in the ordinary way.

## Building it

The data are **not bundled**: they derive from the judge master file, which is
unpublished research material, and from an FJC export that is better downloaded
fresh. Both inputs stay local, as with the CCAD.

```bash
# 1. the FJC export (public).  fjc.gov blocks automated clients, so fetch it
#    in a browser or from your own machine:
curl -LO https://www.fjc.gov/sites/default/files/history/federal-judicial-service.csv
#    or use the download links at
#    https://www.fjc.gov/history/judges/biographical-directory-article-iii-federal-judges-export

# 2. build
python scripts/build_seats.py \
    --fjc federal-judicial-service.csv \
    --master "judge master base 2026 with jcs.dta" \
    --out data/coa
```

The build prints the validation table above; if the 2025 column stops matching
§44, either the FJC release changed its Seat ID scheme or `STATUTORY` in
`build_seats.py` needs updating for a new judgeship act.

The master file must supply `name`, `circuit` (1–11, 12 = D.C., 13 = Federal),
`YearConfirm`, `jcs_2024` and `state_abbrev`. Rows with no circuit are treated as
Supreme Court justices and dropped; `state_abbrev == "ZUSA"` means no home state,
which is correct for the D.C. and Federal Circuits.

## Cross-references

Circuit numbering here follows the JCS scheme (12 = D.C., 13 = Federal), **not**
the CCAD's (0 = D.C., 12 = Federal). `jcs("circuits")` carries both — see
`coa.md`, which also covers the CCAD case data and the SCDB crosswalk.
