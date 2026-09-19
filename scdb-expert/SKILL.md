---
name: scdb-expert
description: Expert on the U.S. Supreme Court Database (SCDB, Spaeth et al.) with the full data bundled - every case 1791-2025 (SCDB Legacy 07 + 2026_01), case-centered and justice-centered by citation, plus codebook value labels, a variable guide, and methodological guidance. Use this skill whenever the user asks about SCDB variables or codes (caseId, issue, issueArea, decisionDirection, lawSupp, decisionType, majVotes, vote, majority, naturalCourt, etc.) or wants counts, trends, or statistics about Supreme Court decisions or justices - voting patterns, agreement rates, dissents, unanimity, 5-4 cases, opinion authorship, reversal rates, cases by issue or lower court, declarations of unconstitutionality, overruled precedents, ideal points / IRT models of the Court - even if the SCDB is not named. Also use it to look up how a specific case is coded, to merge SCDB data with other datasets, or to rebuild the data from a new SCDB release.
---

# Supreme Court Database (SCDB) expert

This skill bundles the complete SCDB (organized by citation) plus the knowledge to
use it well. Answer SCDB questions by **computing from the bundled data**, not
from memory, and say how the sample was defined.

`SKILL_DIR` below means the directory containing this file (in claude.ai usually
`/mnt/skills/user/scdb-expert`; in Claude Code usually `~/.claude/skills/scdb-expert`).
The data work offline — no download needed.

## What's here

| path | contents |
|---|---|
| `data/case_citation.csv.gz` | 29,270 cases × 53 vars, terms 1791–2025 (one row per case) |
| `data/justice_citation.csv.gz` | 256,469 rows × 61 vars (one row per sitting justice per case) |
| `data/MANIFEST.json` | source releases, row counts, checksums |
| `scripts/scdb.py` | Python loader/labeler/search + CLI (pandas) |
| `scripts/scdb.R` | same API for R (`scdb_load`, `scdb_label`, `scdb_factor`, `scdb_find`) |
| `scripts/build_combined.py`, `scripts/parse_codebook.py` | rebuild from new SCDB releases |
| `references/variables.md` | **read first for any variable question**: every variable, codes, missingness, gotchas |
| `references/analysis_guide.md` | sample definition, Legacy vs Modern, direction-coding critiques, vote analysis, IRT, merging |
| `references/data_notes.md` | provenance, what the build changed, known quirks, how to update |
| `references/value_labels.csv` | all 1,571 codes: `variable, code, label, table` |
| `references/justices.csv` | id, name, first/last term, votes, dissents, majority opinions |
| `references/natural_courts.csv` | natural-court codes with observed date ranges and participants |
| `references/codebook_text.md` | full codebook narrative (§1–63), grep by `## 37. Decision Direction` etc. |

## Workflow

1. **Classify the request.**
   - *Case lookup* ("how is Miranda coded?") → CLI `case`/`find`.
   - *Variable/code meaning* → `variables.md`, then `codebook_text.md` for the official rule.
   - *Quantitative question* → load data, define the sample (step 2), compute, report.
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
python SKILL_DIR/scripts/scdb.py cite                 # how to cite the releases
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
```

The case file loads in <1 s; the justice file in ~5 s. Load once per session and
reuse. Needs pandas (`pip install pandas` if missing). Justice rows already carry
all case-level variables, so most vote analyses need no merge.

## R API

```r
source(file.path("SKILL_DIR", "scripts", "scdb.R"))   # finds the data via SCDB_SKILL_DIR or default paths
cases <- scdb_load("case"); votes <- scdb_load("justice")
cases <- scdb_label(cases, "issueArea"); cases$dir_f <- scdb_factor(cases$decisionDirection, "decisionDirection")
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

## When the user wants to update the data

New SCDB releases (scdb.psu.edu) appear most falls. Follow `data_notes.md` →
"Updating": run `build_combined.py --src <folder with the 4 CSVs>`, optionally
`parse_codebook.py <new codebook.pdf>`, then update the release facts in this file
(header description, coverage end date) and repackage the skill.
