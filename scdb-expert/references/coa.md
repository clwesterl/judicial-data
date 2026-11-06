# Courts of Appeals data and the SCDB crosswalk

Read this before any question about courts of appeals cases, about Supreme Court
review of a circuit decision, or about merging the two databases.

## What's bundled

| table | rows | contents |
|---|---|---|
| `coa("cases")` | 512,263 | published U.S. Courts of Appeals opinions, 1880–2025, 28 variables |
| `coa("crosswalk")` | 8,265 | CoA cases linked to an SCDB case, with a confidence tier |

Source: the **Comprehensive Court of Appeals Database** (CCAD), Release 09-2026,
by Eitan Sapiro-Gheiler and Jonathan P. Kastellec (Princeton). The full release is
512,263 rows × **809** columns in a 5.85 GB uncompressed RData file. Only 28
columns are bundled here — the identifiers, panel structure, and the LLM-coded
SCDB-track party/issue/disposition variables needed for linking and for basic
case-level work. Anything else (the per-judge FJC blocks, panel ideology
aggregates, the ~270 `songer_gt_*` hand-coded ground-truth fields, the ~70
`idb_*` administrative fields, the LLM justification text) has to come from the
full file. `scripts/coa_slice.R` extracts a slice; widen its `want` vector and
rerun `scripts/build_coa.py` to bundle more.

## Three circuit numbering schemes — do not mix them

| | D.C. | 1st–11th | Federal |
|---|---|---|---|
| **CCAD** (`coa()` tables) | 0 | 1–11 | 12 |
| **JCS** (`jcs()` tables) | 12 | 1–11 | 13 |
| **SCDB** (`caseSource`, `caseOrigin`) | 32 | 21–31 | 8 |

`jcs("circuits")` carries all three (`circuit`, `coa_circuit`, `scdb_caseSource`).
Always crosswalk through it rather than assuming. CCAD `circuit` is missing for
59,266 cases, nearly all pre-1891 (the courts of appeals were created that year;
earlier rows are the old circuit courts).

## How the crosswalk was built

**Neither database carries the other's citation.** SCDB has no lower-court
citation or docket field, and the CCAD has no SCOTUS citation field. So the link
is necessarily fuzzy, built from three signals (`scripts/build_coa.py`):

1. **Circuit** — SCDB `caseSource` must map to the CoA case's circuit.
2. **Party names** — TF-IDF cosine over 4-character word stems, with Federal
   Reporter abbreviations expanded (`Ins.`→insurance, `Ry.`→railway, ~90 entries).
   Scored **per party and order-insensitively**, because the CoA loser is usually
   the SCOTUS petitioner: the score is `max(√(s₁₁·s₂₂), √(s₁₂·s₂₁))`, so matching
   only one of the two parties scores low. 25% weight goes to a pooled bag-of-words
   score, which rescues cases where one side is renamed.
3. **Time to review** — a log-normal prior on days between the two decisions,
   calibrated on confirmed links (median 441 days, 5th pct 237, 95th pct 745).
   **The prior is floored at 0.6** and the hard window is 30–2,600 days. The floor
   matters: an unfloored prior scored *Leyra v. Denno* (189-day review, exact party
   match) at 0.06 and lost ~10 points of recall. Fast review is real; the date
   should never erase an exact name match.

A link is **mutual** when the CoA case is the SCDB case's best candidate *and* the
SCDB case is the CoA case's best candidate. Tiers:

| tier | rule | recall | false positives |
|---|---|---|---|
| **A** | mutual, score ≥ 0.50 | 63.0% | 0.85% |
| **B** | mutual, score ≥ 0.35 | +7.8 pts | 0.95% cumulative |
| **C** | score ≥ 0.20 | +1.7 pts | 1.00% cumulative |

`add_coa()` / `scdb_add_coa()` default to tier A. Tier A and A+B are one-to-one in
both directions. Tier C introduces 148 CoA cases matched to two SCDB cases; those
are mostly genuine — *General Talking Pictures* (91 F.2d 922) really was decided at
304 U.S. 175 and again at 305 U.S. 124 on rehearing — but inspect before using.

Coverage of SCDB cases whose `caseSource` is a court of appeals (9,947 cases):
68% at tier A, 77% at A+B, 83% at A+B+C.

## Validation

**Against Songer ground truth.** `songer_gt_supct` flags Songer-sampled CoA cases
the Supreme Court later reviewed. Within its window — CoA decisions 1952–1988,
13,587 cases in the Songer sample, 2,855 of them flagged reviewed — the figures
above hold: recall 63–73%, false positives under 1%.

**Independently, against lower-court disposition.** SCDB's `lcDisposition` records
what the court below did; the CCAD's `scdb_first_disposition` records the same
thing from the opinion text. Agreement between them, on the collapsed buckets, by
tier — this check runs across all terms, not just the Songer window:

| tier | n | agreement |
|---|---|---|
| A | 6,582 | **78.2%** |
| B | 811 | 66.1% |
| C | 564 | 52.1% |
| unlinked best candidate | 1,179 | 45.7% |
| chance (marginal product) | | 35.7% |

The step is sharp at the 0.50 threshold (66% below, 78% above), which is what sets
tier A. The residual 22% disagreement in tier A is LLM-vs-coder disagreement about
disposition, not match error.

## Known limits — state these when reporting results

- **Recall is capped near 75%, and the shortfall is structural, not fixable by
  better string matching.** For CoA cases confirmed reviewed but left unlinked,
  dropping the circuit filter and the date window entirely still finds an SCDB case
  scoring >0.7 for only 9% of them. The causes are consolidation (SCOTUS names only
  the lead case, so companion CoA cases share no party names), officeholder
  substitution (*Talbott v. United States ex rel. Toth* in the Fourth Circuit became
  *Toth v. Quarles* at the Court), and SCOTUS dispositions that never became an SCDB
  case.
- **Coverage falls off in recent decades**: tier A links 80% of SCDB circuit-origin
  cases in the 1940s but 58% in the 2010s and 53% in the 2020s. The likely cause is
  that the CCAD covers *published* opinions only, while modern cert grants
  increasingly come from unpublished dispositions. Treat recent-term linkage as
  incomplete in a way that is probably correlated with case type.
- **Before 1925 the match is weaker** (46–55% tier A in the 1890s–1910s): sparser
  CCAD coverage and noisier party names in the old reports.
- **`coa_citation` is missing for 217 linked cases**, all from the 2010s (6%) and
  2020s (100%) — F.4th volumes unassigned when the CCAD was built. `coa_caseid`
  still links correctly.
- **`songer_gt_supct == 0` is not a reliable negative.** The CCAD codebook says
  Phase 2 "by construction enumerates every Courts-of-Appeals case subsequently
  reviewed by the Supreme Court," but it does not. Confirmed counterexamples found
  here, all flagged 0: *Service v. Dulles*, 235 F.2d 215 (D.C. Cir. 1956), reversed
  at 354 U.S. 363; *Storer Broadcasting*, 220 F.2d 204, at 351 U.S. 192;
  *Massachusetts Bonding & Insurance*, 227 F.2d 385, at 352 U.S. 128; *FPC v.
  Memphis Light, Gas & Water*, 462 F.2d 853, at 411 U.S. 458. Use the flag for
  recall; do not treat a 0 as proof a case was never reviewed.

## Code schemes: two remaps you must apply

**Disposition.** The CCAD documents its disposition columns as using "the SCDB
scheme," but the numbering is a *permutation* of SCDB's, not a copy. Codes 1–8 sit
one below SCDB's, and 9 and 0 wrap around:

| CCAD | meaning | SCDB |
|---|---|---|
| 1 | affirmed | 2 |
| 2 | reversed | 3 |
| 3 | reversed and remanded | 4 |
| 4 | vacated and remanded | 5 |
| 5 | affirmed in part, reversed in part | 6 |
| 6 | affirmed in part, reversed in part, and remanded | 7 |
| 7 | vacated | 8 |
| 8 | petition denied or appeal dismissed | 9 |
| 9 | stay, petition, or motion granted | 1 |
| 10 | certification | 10 |
| 0 | no disposition / ambiguous | 11 |
| 11 | affirmed, vacated, and remanded | *no SCDB equivalent* |

Use `coa_disposition_to_scdb()` / `scdb_coa_disposition()`. Merging without it
silently shifts every disposition by one category.

**Direction.** Every CCAD "direction" variable uses the **Songer** convention
(0 = not ascertained, 1 = conservative, 2 = mixed, 3 = liberal), *not* SCDB's
(1 = conservative, 2 = liberal, 3 = unspecifiable). Use
`songer_direction_to_scdb()` / `scdb_songer_direction()`; mixed collapses into 3,
which loses information, so for direction-sensitive work keep the Songer coding and
say which convention you used.

## Other CCAD cautions

- The substantive variables bundled here (`scdb_first_*`) are **LLM-coded from
  opinion text**, not hand-coded. The source codebook reports per-variable
  validation accuracy against Songer and SCDB ground truth; cite it rather than
  treating these as equivalent to hand coding.
- The recommended clean-panel filter is
  `judge_count == 3 & all_judges_matched == 1 & all_authors_matched == 1`.
  `judge_count == 3` already excludes en banc cases, so a separate `is_enbanc == 0`
  is redundant.
- One row is one published opinion-bearing case, so rehearings can appear as
  separate rows for the same litigation.
- `songer_gt_casenum` is not unique in the full file (two KH-update collisions);
  use `caseid`.

## Usage

```python
import scdb
cases = scdb.coa("cases")                 # 512,263 CoA cases
x     = scdb.coa("crosswalk")             # 8,265 links

c = scdb.add_coa(scdb.load("case"))       # SCDB + the reviewed CoA case (tier A)
d = scdb.add_scdb(cases)                  # CoA + the reviewing SCOTUS case
c = scdb.add_coa(scdb.load("case"), confidence=("A", "B"))

cases["disp_scdb"] = scdb.coa_disposition_to_scdb(cases.scdb_first_disposition)
```

```r
source("scripts/scdb.R")
cases <- scdb_coa("cases"); x <- scdb_coa("crosswalk")
c <- scdb_add_coa(scdb_load("case"))      # tier A by default
d <- scdb_add_scdb(cases)
cases$disp_scdb <- scdb_coa_disposition(cases$scdb_first_disposition)
```

## Rebuilding

```bash
Rscript scripts/coa_slice.R               # needs R and the 5.85 GB RData (~6-8 GB RAM)
python scripts/build_coa.py --coa coa_link.csv.gz
```
`build_coa.py` writes deterministic gzip (mtime 0), so an unchanged source rebuilds
byte-identically. `data/coa/MANIFEST.json` records row counts, SHA-256 digests, and
the matcher settings used.

## Citation

> Eitan Sapiro-Gheiler and Jonathan P. Kastellec. Comprehensive Court of Appeals
> Database, Release 09-2026. Princeton University.

The companion paper is "Appealing to Large-Language-Model-as-Judge: Annotating and
Analyzing the Universe of U.S. Appellate Opinions." The CCAD also redistributes the
Songer Courts of Appeals Database and the FJC Integrated Database; cite those
separately when using `songer_gt_*` or `idb_*` fields. The crosswalk itself is
derived here and is not part of either source release — describe it as a fuzzy
match with the tier and the validation figures above, not as an official linkage.
