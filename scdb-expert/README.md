# scdb-expert (Claude skill)

Federal courts expert with three databases bundled and cross-linked:

- **Supreme Court Database** — SCDB Legacy 07 + 2026_01, citation-organized,
  terms 1791–2025, case- and justice-centered
- **Judicial Common Space** — justice-term scores OT1937–2022, 693 appeals judges,
  Court/House/Senate/president/circuit medians 1924–2024
- **Comprehensive Court of Appeals Database** — 512,263 published opinions
  1880–2025 (74 of the CCAD's 809 columns, including panel rosters and ideology),
  plus 8,265 CoA cases linked to the Supreme Court case that reviewed them

Claude reads `SKILL.md`; this file is for humans.

## Install

**claude.ai / Claude desktop app (any computer you sign into):**
Customize → Skills → "+" → upload `scdb-expert.skill` (or a zip of this folder).
Requires "Code execution and file creation" in Settings → Capabilities.
Uploaded skills are private to your account and follow you across devices.

**Claude Code (per machine):** put this folder at `~/.claude/skills/scdb-expert/`.
To keep machines in sync, keep the folder in a git repo and symlink it:

```bash
ln -s /path/to/repo/skills/scdb-expert ~/.claude/skills/scdb-expert
```

The data files are ~44 MB gzipped (37 MB of that is the courts of appeals
case file), fine for GitHub.

**Using the data outside Claude:** `data/*.csv.gz` are plain gzipped CSVs;
`readr::read_csv()`, `data.table::fread()` (with R.utils), and `pandas.read_csv()`
read them directly. `scripts/scdb.R` and `scripts/scdb.py` add typing and labels.

## Interactive coalition graph

```bash
python scripts/build_coalition_page.py --start 1946 --end 2025 --out ../docs/scotus_coalitions.html
```

Writes one self-contained HTML file: each node is a set of justices who formed a
majority, sized by case count. Drill down chief justice → natural court → term, plus
justice highlighting and a minimum-cases filter. Any range works (`--start 1953 --end
1968`); the whole database (`--start 1791`) builds but is ~14 MB and slow to render.
Needs internet on first open (d3 from a CDN).

## Coalitions ranked by majority ideology

```bash
python scripts/build_coalition_ranking.py --start 1946 --end 2022 --out ../docs/scotus_coalition_ranking.html
```

Same coalitions as the graph above, but as a ranked dot plot: each row is a majority
coalition placed at the median JCS score of the justices in it, with a membership
strip, the term-to-term spread of its per-case medians, and its case count. End term
is capped at OT2022, where JCS justice scores stop.

Two ways to read the x-axis: `median ideology` places each coalition on the JCS scale
with the scope's Court median as a dashed reference, and `distance from Court median`
re-centres on zero so each dot is the gap between the majority and the Court median of
that case's own term. In the first mode, `mark Court median per row` adds a tick at the
Court median each coalition actually faced.

## Update to a new SCDB release

In the judicial-data repo the original release files live in `../scdb-raw/`
(gzipped; the build reads .csv or .csv.gz).

```bash
python scripts/build_combined.py --src ../scdb-raw   # or any folder with the 4 citation CSVs
python scripts/parse_codebook.py ~/Downloads/SCDB_YYYY_RR_codebook.pdf   # only if codebook changed
```

For a new Judicial Common Space release: `python scripts/build_jcs.py --src ../jcs-raw`.

For a new Courts of Appeals release — the CCAD ships as a 5.85 GB uncompressed
RData file, so this step needs R and ~6–8 GB of RAM, and cannot run inside the
skill:

```bash
Rscript scripts/coa_slice.R                       # run where the RData lives
python scripts/build_coa.py --coa coa_link.csv.gz
```

`coa_slice.R` pulls the 74 bundled columns out of the 809; widen its `want` vector
to bundle more and `build_coa.py` picks them up automatically. Re-check the three
CCAD code-scheme quirks in `references/data_notes.md` against the new data — they
are errors in the CCAD codebook, so a new release may fix or move them.

Then update the release facts in `SKILL.md` and `references/data_notes.md`, and
re-upload / commit. Details in `references/data_notes.md`.
