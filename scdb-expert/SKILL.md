---
name: "scdb-expert"
description: Expert on judicial politics data, bundled and cross-linked: the U.S. Supreme Court Database (SCDB, every case 1791-2025), Judicial Common Space ideology scores (justices, appeals judges, Court/House/Senate/president/circuit medians), the Comprehensive Court of Appeals Database (512,263 opinions 1880-2025, linked to the SCDB; judgeship succession), and Kritzer's state supreme court election archive (1936-2023). Use whenever the user asks about SCDB variables or codes (issueArea, decisionDirection, vote, naturalCourt); counts or trends in Supreme Court decisions and votes (agreement, dissents, 5-4 cases, reversals, laws struck down, overrulings); judicial ideology (JCS, Martin-Quinn, the Court median vs Congress or president, circuit medians, IRT); circuit decisions, panels and their Supreme Court review; who held a judgeship; or state judicial elections (partisan, nonpartisan, retention, vote shares, defeats, how a state picks its high court), even if no database is named. Also case lookups, merges, rebuilds.
---

# Supreme Court Database (SCDB) + Judicial Common Space + courts of appeals + state elections expert

This skill bundles the complete SCDB (organized by citation), the Judicial Common
Space (JCS) ideology scores, a slice of the Comprehensive Court of Appeals
Database (CCAD), and Kritzer's State Supreme Court Election Archive, all linked
to each other, plus the knowledge to use them well.
Answer questions by **computing from the bundled data**, not from memory, and say
how the sample was defined.

`SKILL_DIR` below means the directory containing this file (in claude.ai e.g.
`/mnt/skills/plugins/scdb-expert` or `/mnt/skills/user/scdb-expert`; in Claude Code
usually `~/.claude/skills/scdb-expert`).
The data work offline — no download needed.

## What's here

| path | contents |
|---|---|
| `data/case_citation.csv.gz` | 29,270 cases × 53 vars, terms 1791–2025 (one row per case) |
| `data/justice_citation.csv.gz` | 256,469 rows × 61 vars (one row per sitting justice per case) |
| `data/MANIFEST.json` | source releases, row counts, checksums |
| `data/jcs/` | Judicial Common Space: justice-term scores (OT1937–2022), 693 appeals judges, medians by year 1924–2024, circuit↔SCDB crosswalk |
| `data/coa/` | Courts of Appeals: 512,263 published opinions 1880–2025 (74 of the CCAD's 809 vars, incl. panel rosters and GHP ideology); 8,265 CoA↔SCDB links with confidence tiers; 203 judgeships and 868 occupancies, 1891–present |
| `data/state/` | State supreme court elections (Kritzer): 2,672 contested and general elections 1946–2023, 2,302 seats, 896 retention votes 1936–2022; derived selection-method spans by state; state ↔ SCDB `caseSourceState` crosswalk; log of 76 corrections |
| `scripts/scdb.py` | Python loader/labeler/search + CLI (pandas) |
| `scripts/scdb.R` | same API for R (`scdb_load`, `scdb_label`, `scdb_factor`, `scdb_find`) |
| `scripts/build_combined.py`, `scripts/parse_codebook.py`, `scripts/build_jcs.py`, `scripts/build_coa.py`, `scripts/coa_slice.R` | rebuild from new SCDB / JCS / CCAD releases |
| `scripts/build_seats.py`, `scripts/matchjcs.py` | rebuild the seat tables from `fjc-raw/` + the bundled JCS scores |
| `scripts/build_state_elections.py`, `scripts/un7z.py` | rebuild the state tables from `state-elections-raw/` (Kritzer's `.7z` files; `un7z.py` reads 7z with the standard library) |
| `scripts/build_coalition_page.py` | one-file interactive page: majority coalitions as a graph, filterable by term, natural court and justice |
| `references/variables.md` | **read first for any variable question**: every variable, codes, missingness, gotchas |
| `references/analysis_guide.md` | sample definition, Legacy vs Modern, direction-coding critiques, vote analysis, IRT, merging |
| `references/data_notes.md` | provenance, what the build changed, known quirks, how to update |
| `references/value_labels.csv` | all 1,571 codes: `variable, code, label, table` |
| `references/justices.csv` | id, name, first/last term, votes, dissents, majority opinions |
| `references/natural_courts.csv` | natural-court codes with observed date ranges and participants |
| `references/codebook_text.md` | full codebook narrative (§1–63), grep by `## 37. Decision Direction` etc. |
| `references/jcs.md` | **read for any ideology/JCS question**: what the scores are, SCDB links, caveats, quirks, citations |
| `references/coa.md` | **read for any courts-of-appeals or SCOTUS-review question**: what's bundled, how the crosswalk was built and validated, the code-scheme corrections, coverage limits |
| `references/coa_value_labels.csv` | all 382 CCAD codes: `variable, code, label, table` |
| `references/coa_seats.md` | **read for judgeship succession**: what a seat is, FJC Seat IDs, why occupancy ends at senior status, validation against 28 U.S.C. §44 |
| `references/state_elections.md` | **read for any state judicial election question**: tables and keys, election types, the partisan correlation, what the build corrected, known quirks, how selection spans are derived, linking to the SCDB |
| `references/state_value_labels.csv` | all state-election codes: `table, variable, code, label` |

## Workflow

1. **Classify the request.**
   - *Case lookup* ("how is Miranda coded?") → CLI `case`/`find`.
   - *Variable/code meaning* → `variables.md`, then `codebook_text.md` for the official rule.
   - *Quantitative question* → load data, define the sample (step 2), compute, report.
   - *Ideology / JCS* (justice scores, Court median vs Congress/president, circuit
     medians, appeals judges) → `jcs.md`, then the JCS helpers below.
   - *Courts of appeals* (circuit decisions, panels, en banc, which circuit a case came
     from, Supreme Court review of a circuit decision, merging CoA and SCDB data) →
     `coa.md` **first** (it carries two mandatory code remaps), then the CoA helpers below.
   - *Judgeship succession and individual CoA judges* (who held or holds a seat,
     who replaced whom, a judge's tenure and ideology, how a circuit's seats
     turned over, who sat on a circuit in a given year) → `coa_seats.md`, then
     the seat helpers below.
   - *State supreme court elections* (a state justice's elections or retention
     votes, contested vs uncontested races, defeats, partisan vs nonpartisan vs
     retention systems, when a state switched, whether a Supreme Court case came
     from an elected state court) → `state_elections.md`, then the state helpers below.
   - *Research design / methods* → `analysis_guide.md`.
   - *New release / rebuild* → `data_notes.md` "Updating".
2. **Define the sample explicitly** before computing (see analysis_guide.md §1).
   Defaults unless the user says otherwise:
   - formally decided, orally argued cases: `decisionType in {1, 6, 7}`;
   - time unit = `term`;
   - justice votes: participating merits votes, `vote in {1,2,3,4,5}` (excludes cert-denial
     dissents 6, jurisdictional dissents 7, equally divided 8, and non-participants);
   - direction analyses drop unspecifiable (3) / blank.
   State these choices in the answer, and flag when Legacy (≤1945) and Modern data are pooled.
3. **Compute with the helpers** (below); show the key code when the user may want to
   reproduce it — in R if they work in R.
4. **Report** results with the denominator, the filter, and the release
   (`python SKILL_DIR/scripts/scdb.py cite` gives citations). Distinguish SCDB coding
   from legal reality ("the SCDB codes this outcome liberal").

## Quick commands (CLI)

```bash
python SKILL_DIR/scripts/scdb.py info                 # releases & coverage
python SKILL_DIR/scripts/scdb.py find "citizens united"
python SKILL_DIR/scripts/scdb.py find "384 U.S. 436"  # any reporter cite, caseId, docket, name
python SKILL_DIR/scripts/scdb.py case 1965-122        # labeled record + each justice's vote
python SKILL_DIR/scripts/scdb.py labels issueArea     # code table for a variable
python SKILL_DIR/scripts/scdb.py justice kennedy      # service dates, votes, dissents, opinions
python SKILL_DIR/scripts/scdb.py jcs kennedy          # JCS scores: justice by term + appeals judges
python SKILL_DIR/scripts/scdb.py seat reinhardt       # a CoA judge's seat, tenure, predecessor, chain
python SKILL_DIR/scripts/scdb.py state AZ             # a state's selection history + election counts
python SKILL_DIR/scripts/scdb.py state "rose bird"    # every election a state justice stood in
python SKILL_DIR/scripts/scdb.py cite                 # how to cite every bundled source
python SKILL_DIR/scripts/build_coalition_page.py --start 2005 --end 2025 --out coalitions.html
```

## Python API

```python
import sys; sys.path.insert(0, "SKILL_DIR/scripts")
import scdb
c = scdb.load("case")          # coded vars -> Int64, dates -> datetime, ids/names -> str
v = scdb.load("justice")       # 25 legacy placeholder rows dropped by default
c = scdb.label(c, ["issueArea", "decisionDirection"])   # adds issueArea_label, ...
scdb.labels("vote")            # {1: 'voted with majority or plurality', ...}
scdb.find(c, "Dobbs")          # name search handles curly quotes
scdb.best_cite(c)              # U.S. cite, else S. Ct., L. Ed., LEXIS (recent cases lack U.S.)

# default samples
fd = scdb.formally_decided(c)                  # decisionType in {1,6,7}; include_equally_divided=True adds 5
mv = scdb.merits_votes(scdb.formally_decided(v))   # vote in {1..5}
# pairwise agreement (on `majority` by default) + joint-case counts
rate, n = scdb.agreement(mv[(mv.term >= 2023) & (mv.minVotes > 0)],
                         ["CThomas", "SAAlito", "EKagan"], return_n=True)

# Judicial Common Space (see references/jcs.md)
scdb.jcs("justice")            # term, justice, justiceName, jcs   (also "coa", "medians",
                               #   "circuit_medians", "circuits")
v = scdb.add_jcs(v)            # justice's JCS score that term (OT1937-2022; else <NA>)
c = scdb.add_medians(c)        # sc_median, president, house_median, senate_median by term
c = scdb.add_circuit_medians(c, year_offset=0)   # median/SD of the reviewed circuit (caseSource)

# Courts of appeals (see references/coa.md -- read it before merging)
scdb.coa("cases")              # 512,263 CoA opinions 1880-2025
scdb.coa("crosswalk")          # 8,265 CoA<->SCDB links, confidence A/B/C
c = scdb.add_coa(c)            # SCDB + the reviewed CoA case (tier A; confidence=("A","B") to widen)
d = scdb.add_scdb(scdb.coa("cases"))            # CoA + the reviewing SCOTUS case
d = scdb.add_coa_circuit_medians(d)            # + the circuit's JCS median that year
# Judgeships and who held them (see references/coa_seats.md)
scdb.seats()                   # 203 judgeships: creating statute, span, occupants
scdb.seats("spells")           # 868 occupancies: predecessor, ideology shift, exit
scdb.seat_panel(1950, 2026)    # circuit x seat x year, derived from the spells
scdb.find_judge("reinhardt")   # a judge's seats -- the CoA analogue of justice()
scdb.seat_history(1, 3)        # everyone who has held First Circuit seat 3
scdb.court_composition(9, 1995)  # who sat on the Ninth in 1995, by seat

# State supreme court elections (see references/state_elections.md)
scdb.state_elections("elections")   # also "seats", "retention", "selection", "states", "fixes"
scdb.state_candidates()             # one row per candidate: votes, share, rank, party, incumbency
scdb.find_state_judge("durham")     # every election (contested, unopposed, retention) by name
scdb.state_selection("NC", 2010)    # ['nonpartisan']; [] = not elected; None = archive can't say
c = scdb.add_state_selection(c)     # + source_state, state_selection for caseSource == 300
scdb.label_state(df, table="seats") # <var>_label columns; scdb.state_labels("Party")

scdb.coa_labels("scdb_first_broad_area"); scdb.label_coa(d)   # code -> label
scdb.coa_disposition_to_scdb(d.scdb_first_disposition)   # CCAD codes are NOT SCDB codes
scdb.songer_direction_to_scdb(x)                # for songer_gt_* fields ONLY
```

The case file loads in <1 s; the justice file in ~5 s. Load once per session and
reuse. Needs pandas (`pip install pandas` if missing). Justice rows already carry
all case-level variables, so most vote analyses need no merge.

## R API

```r
source(file.path("SKILL_DIR", "scripts", "scdb.R"))   # finds the data via SCDB_SKILL_DIR or default paths
cases <- scdb_load("case"); votes <- scdb_load("justice")
cases <- scdb_label(cases, "issueArea"); cases$dir_f <- scdb_factor(cases$decisionDirection, "decisionDirection")
votes <- scdb_add_jcs(votes); cases <- scdb_add_medians(cases); coa <- scdb_jcs("coa")
appeals <- scdb_coa("cases"); link <- scdb_coa("crosswalk")
cases <- scdb_add_coa(cases)                      # + the reviewed CoA case (tier A)
appeals <- scdb_add_scdb(appeals)                 # + the reviewing SCOTUS case
appeals <- scdb_add_coa_circuit_medians(appeals)  # + the circuit's JCS median that year
appeals <- scdb_coa_label(appeals)                # adds <var>_label columns
appeals$disp_scdb <- scdb_coa_disposition(appeals$scdb_first_disposition)
judgeships <- scdb_seats(); occupancies <- scdb_seats("spells")
panel <- scdb_seat_panel(1950); scdb_seat_history(1, 3); scdb_court_composition(9, 1995)
elect <- scdb_state("elections"); ret <- scdb_state("retention"); cand <- scdb_state_candidates()
cases <- scdb_add_state_selection(cases); scdb_state_labels("electtype", "elections")
```

## Essentials to keep in mind

- **Citation-level data**: lead docket and *first* issue/legal provision only. Docket-
  or issue-level questions need other SCDB files — say so rather than approximate silently.
- **Legacy ≠ Modern**: Legacy (1791–1945) was coded retrospectively, has only the
  first issue, sparse legal provisions (54% "no legal provision"), a mandatory
  docket before 1925, and 18% unspecifiable direction. Show eras separately for long series.
- **Direction** is defined relative to the issue with non-obvious conventions
  (economic: liberal = pro-government/anti-business; federalism: liberal = pro-federal).
  Mention published critiques when conclusions hinge on it (analysis_guide.md §3).
- **Justice file includes non-participants** (blank vote). `majority`: 2 = majority, 1 = dissent.
- **Equally divided cases**: case file shows 4–4/3–3; justice rows have vote 8, blank majority.
- **Keys**: `lexisCite` is the unique cite; `usCite` is missing for many cases from OT2016 on.
  `justice` ids match SCDB ids used elsewhere (renumbered in 2012).
- **Undocumented codes** (caseOrigin 154/156/157/158/161; agreement = 0): report as unlabeled.
- **Coverage ends** with decisions of June 30, 2026 (OT2025). For later events, say the
  data stop there and use web search if available; don't extrapolate.
- Counting laws struck down (`declarationUncon`) or overrulings (`precedentAlteration`)
  counts *cases*, not laws or precedents.
- Opinion assigner is inferred, wrong ~16% of the time per the codebook.
- **JCS**: scale ≈ −1 liberal to +1 conservative. Justice scores are vote-based and
  time-varying (end OT2022, so OT2023–2025 get none); appeals judges' scores are fixed,
  appointment-based (Giles–Hettinger–Peppers). Medians row for term t is calendar year
  t+1. Using justice scores to explain the same votes they were estimated from is
  partly circular — say so and suggest lags. Cite Epstein, Martin, Segal & Westerland (2007).
- **Courts of appeals** (read `coa.md` before any merge — these bite silently):
  - **Three circuit numberings.** CCAD: 0 = D.C., 1–11, 12 = Federal. JCS: 12 = D.C.,
    13 = Federal. SCDB `caseSource`: 32 = D.C., 21–31, 8 = Federal. Crosswalk through
    `jcs("circuits")`, never by assumption.
  - **CCAD disposition codes are a permutation of SCDB's**, not a copy (1–8 sit one
    below SCDB's; 9 and 0 wrap). Always `coa_disposition_to_scdb()`.
  - **The CCAD's LLM direction columns are already in SCDB coding** (1 cons, 2 lib,
    3 unspecifiable) despite the codebook saying otherwise — do NOT remap them.
    `songer_direction_to_scdb()` is for the `songer_gt_*` fields only. Reading them
    as Songer-coded makes liberal decisions vanish into "mixed". Prefer
    `scdb_second_direction_mech` over `scdb_first_direction_oneshot`.
  - **The crosswalk is a fuzzy match**, not an official linkage: neither database
    carries the other's citation. Tier A is ~0.9% false positives and links 68% of
    SCDB circuit-origin cases; report the tier and that it is a derived match.
    Linkage is weakest for recent terms (53% in the 2020s) because the CCAD covers
    published opinions only — so it is incomplete in a way correlated with case type.
  - **`songer_gt_supct == 0` does not mean "never reviewed"** — confirmed
    counterexamples are in `coa.md`. Use it for recall, not as a negative.
  - CCAD substantive variables are **LLM-coded from opinion text**, not hand-coded.
  - **The CoA case file may live outside the skill.** `coa_cases.csv.gz` is 37 of
    the bundle's 43 MB, so an upload may ship without it. `coa("cases")` then
    looks under `$SCDB_DATA_EXTRA` at the same relative path and, failing that,
    raises an error naming both paths. If that happens, tell the user to set
    `SCDB_DATA_EXTRA` to a `data/` directory holding the file (their clone of
    the judicial-data repo) — everything else, seats included, still works.
  - Coded CCAD variables have labels: `coa_labels(v)`, `label_coa(df)`, and
    `coa_labelled_vars()` — the CoA analogue of `labels()` / `label()`.
    `scdb_first_broad_area` and `scdb_second_sub_area` reuse SCDB's `issueArea` /
    `issue` code lists exactly; the party-category scale does not.
  - Clean panels: `judge_count == 3 & all_judges_matched == 1 & all_authors_matched == 1`.
  - **Judges**: `author` is a panel-slot index (1/2/3), not a judge id — use
    `author_id` / `author_name`. `author_ghp` and the `ghp_*` panel aggregates are
    Giles–Hettinger–Peppers scores, the same measure behind the JCS appeals-judge
    scores, so panels and circuits sit on one scale; `add_coa_circuit_medians()`
    attaches the circuit's JCS median so `ghp_med - circuit_median` is how far a
    panel sat from its circuit. For author-level work filter `is_percuriam != 1`
    (16.1% of cases are per curiam); that alone makes `author_id`/`author_name`
    complete. `all_authors_matched == 1` does **not** — it drops only 0.9% and
    still leaves 18.6% of authors unnamed. `author_ghp` is missing for a further
    3.1%, judges with no GHP score.

- **State elections** (read `state_elections.md`):
  - **Three tables, three units**: Elections has one row per contest (a seat can
    have primaries, run-offs and a general), Seats one per seat, Retention one per
    yes/no vote. Montana and Utah's unopposed incumbents who faced a yes/no vote
    (`electtype` 11, 28 elections) are in all three. Decide whether to count them
    once or twice.
  - **State naming differs**: `state` is the postal code in Elections and Seats;
    in Retention it is a 1–20 sequence and `state2` is the postal code.
    `stateid` (1–50) is common to all three.
  - **No person IDs.** Names are free text and spelled inconsistently; match on
    surnames with `find_state_judge()` and check the hits.
  - **Nonpartisan `correlation`s are absolute values**, not signed. Seats `Pct*`
    are 0–100; Retention `pct_yes` is 0–1.
  - **Retention defeats are in `notes`**, not `pct_yes < .5`: Illinois requires
    60% yes and New Mexico 57%.
  - The build corrected 76 archive errors (`fixes.csv`), including Arizona's
    2022 retention counts, which were copied from 2020. 16 retention rows with
    inconsistent `pct_yes` and 23 Election/Seats year mismatches are left as is
    and listed in the manifest.
  - **`selection.csv` and `add_state_selection()` are derived** from the elections
    observed, not taken from the archive. The switch years are approximate (the
    first election under the new system), and `"none"` merges every
    non-elective system. State court cases reach the SCDB as `caseSource` 300
    plus `caseSourceState`. The method describes how the *court* was chosen,
    not the justices who decided the case.
  - County-level returns and the justice lists are in the raw state workbooks
    (`state-elections-raw/AllFiles.7z`), not in the tables. `un7z.read()` opens
    them.

## When the user wants to update the data

New SCDB releases (scdb.psu.edu) appear most falls. Follow `data_notes.md` →
"Updating": run `build_combined.py --src <folder with the 4 CSVs>`, optionally
`parse_codebook.py <new codebook.pdf>`, then update the release facts in this file
(header description, coverage end date) and repackage the skill.

New CCAD releases: run `coa_slice.R` on a machine with R and the RData (the full
file is 5.85 GB and needs ~6–8 GB of RAM), then
`python scripts/build_coa.py --coa coa_link.csv.gz`. See `coa.md` → "Rebuilding".

New Kritzer releases: put the `.7z` files in `state-elections-raw/` and run
`python scripts/build_state_elections.py --raw ../state-elections-raw --out data/state`.
A correction the new release already made stops the build with "found X,
expected Y"; delete that entry from `FIXES`. See `state_elections.md` →
"Rebuilding".
