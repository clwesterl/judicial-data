# judicial-data

Judicial politics data, harmonized and cross-linked, plus a Claude skill that
knows how to use it.

Three databases are combined here, each kept in its original form alongside a
cleaned, linked build:

| database | coverage | unit |
|---|---|---|
| **Supreme Court Database** (SCDB) | every case, 1791–2025 | case and justice-vote |
| **Judicial Common Space** (JCS) | justices OT1937–2022, 693 appeals judges, institutional medians 1924–2024 | judge-term |
| **Comprehensive Court of Appeals Database** (CCAD) | 512,263 published opinions, 1880–2025 | case |

The three are linked: JCS scores attach to SCDB justice-votes and to the circuit
a case came from, and 8,265 courts of appeals cases are matched to the Supreme
Court case that reviewed them.

## Layout

```
scdb-expert/          the Claude skill: data, loaders (Python + R), reference docs
  data/               combined SCDB, JCS tables, CoA slice and crosswalk
  scripts/            scdb.py, scdb.R, rebuild scripts, page builders
  references/         variables, analysis guide, JCS notes, CoA notes, codebook text
scdb-raw/             the original SCDB releases (Legacy 07, 2026_01) + codebook
docs/                 interactive pages, viewable on GitHub Pages
```

## Using the skill

Install it for Claude Code by symlinking into your skills directory:

```bash
git clone https://github.com/clwesterl/judicial-data.git
ln -s "$PWD/judicial-data/scdb-expert" ~/.claude/skills/scdb-expert
```

Then ask questions in plain language — "how often did Black and Douglas agree on
free speech cases", "number of precedents overturned by year since 1953", "which
circuit decisions did the Court reverse most often" — and the skill computes from
the bundled data rather than from memory.

## Using the data directly

Python:

```python
import sys; sys.path.insert(0, "scdb-expert/scripts")
import scdb

cases  = scdb.load("case")          # 29,270 cases x 53 vars
votes  = scdb.load("justice")       # 256,469 justice-votes x 61 vars
votes  = scdb.add_jcs(votes)        # + each justice's JCS score that term
cases  = scdb.add_coa(cases)        # + the courts of appeals case reviewed
appeals = scdb.coa("cases")         # 512,263 CoA opinions
```

R:

```r
source("scdb-expert/scripts/scdb.R")
cases   <- scdb_load("case")
votes   <- scdb_add_jcs(scdb_load("justice"))
cases   <- scdb_add_coa(cases)
appeals <- scdb_coa("cases")
```

Both APIs mirror each other. `scdb-expert/references/` documents every variable,
the default sample definitions, and the gotchas — read `coa.md` before merging
Supreme Court and courts of appeals data, because the two use different disposition
and direction code schemes.

## Interactive pages

`docs/` holds two self-contained pages built from the data:

- **`scotus_coalitions.html`** — every majority coalition OT1946–OT2025 as a force
  graph: one node per unique coalition, sized by how often it formed, filterable by
  term, natural court, chief justice and justice. Click a node for the case list.
  8,216 cases, 1,575 distinct coalitions.
- **`scotus_coalition_ranking.html`** — the same coalitions ranked by the JCS median
  of the majority, with the Court median overlaid. 8,040 cases (ends OT2022, where
  the JCS justice scores end).

Rebuild either with `scdb-expert/scripts/build_coalition_page.py` or
`build_coalition_ranking.py`.

## Rebuilding from new releases

```bash
# SCDB (new release most falls, scdb.psu.edu)
python scdb-expert/scripts/build_combined.py --src <folder with the 4 CSVs>

# Judicial Common Space
python scdb-expert/scripts/build_jcs.py --src <folder with the JCS CSVs>

# Courts of Appeals -- needs R and the 5.85 GB RData (~6-8 GB RAM)
Rscript scdb-expert/scripts/coa_slice.R
python scdb-expert/scripts/build_coa.py --coa coa_link.csv.gz
```

Every build writes deterministic gzip (mtime 0) and a `MANIFEST.json` with row
counts and SHA-256 digests, so an unchanged source rebuilds byte-identically.

## Citing

Run `python scdb-expert/scripts/scdb.py cite` for the current list. The sources
are cited separately from this repository; the SCDB↔CoA crosswalk is derived here
and is not part of any source release — describe it as a fuzzy match, with the
confidence tier and the validation figures in `references/coa.md`.
