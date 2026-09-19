# Data notes: provenance, harmonization, known quirks

## Provenance

Built by `scripts/build_combined.py` from the official SCDB citation-organized CSVs
(exact files, row counts, and SHA-256 checksums are in `data/MANIFEST.json`):

| era | release | terms | case rows | justice rows |
|---|---|---|---|---|
| Legacy | SCDB_Legacy_07 (Oct 1, 2021) | 1791–1945 | 19,861 | 172,213 |
| Modern | SCDB_2026_01 | 1946–2025 (last decision 2026-06-30) | 9,409 | 84,256 |
| **combined** | | 1791–2025 | **29,270** | **256,469** |

Value labels and codebook text come from the SCDB 2023_01 codebook (the latest one
supplied). Every code in the 2026_01 data has a label in that codebook except
those listed under "Undocumented codes" below.

The SCDB is now hosted by Penn State (scdb.psu.edu / scdb.la.psu.edu), formerly
Washington University in St. Louis (scdb.wustl.edu). Modern releases usually
appear each fall after the term ends; Legacy releases are infrequent.

## What the build changed (and didn't)

The schema is identical to the official files (53 case columns; 61 justice
columns = the 53 plus 8 justice-level variables). Changes:

1. **Encoding.** Legacy CSVs are cp1252 (a `§` in lawMinor breaks UTF-8 readers);
   all output is UTF-8.
2. **Missing values.** Legacy files write the literal `NULL` (lawMinor in 16,106
   Legacy cases; voteId on the 25 placeholder rows). Converted to blank, matching
   the Modern convention. After the build, blank = missing everywhere.
3. **Order.** Stable sort by caseId, so the files run chronologically by term;
   justice order within each case is untouched.

Verified: after steps 1–3, the combined files equal the concatenated sources
row-for-row. No other values were altered, recoded, or imputed.

## Known quirks

**25 placeholder rows (justice file only).** Legacy equally divided cases
(decisionType 5) with no recorded votes appear in the justice file as a single
row with `justice = -99`, `justiceName = "-99"`, blank voteId, `splitVote = -99`.
They have no case-file record (hence 29,295 caseIds in the justice file vs
29,270 in the case file). `scdb.load("justice")` drops them by default.

**Equally divided cases generally.** Case file reports majVotes/minVotes as 4–4
(175 cases) or 3–3 (10); justice rows have `vote = 8` and blank `majority`.

**Non-participation.** Non-participating justices have rows with blank vote,
opinion, direction, and majority. Votes 6 and 7 are treated as non-participation
on the merits by the codebook but carry `majority = 1`.

**Undocumented codes.**
- `caseOrigin` 154, 156, 157, 158, 161 — 7 Modern cases (e.g. 1982-092, 1988-038,
  1994-049, 2001-002, 2001-008, 2001-022, 2005-004). No label in the codebook;
  report as "unlabeled" rather than guessing.
- `firstAgreement` / `secondAgreement` = 0 — about 2,700 / 2,800 rows, both
  eras. Not a justice id; treat as "no join recorded".

**Missing U.S. Reports cites.** Roughly 30–75 cases per term from OT2016 onward
lack `usCite` (volumes not yet paginated when the release was built). Use
`sctCite`, `ledCite`, or `lexisCite`.

**Case names.** Modern names use typographic apostrophes/quotes (’ “ ”);
`scdb.find` normalizes them. Legacy names come from Lawyers' Edition and may
differ from common short names.

**Natural court codes** don't always match observed membership (see
`natural_courts.csv` and analysis_guide.md §1). Natural courts 101 (Jay 1) and
1708 (Roberts 8, the post-Ginsburg vacancy) have no decided cases.

**lawMinor** is free text with stray values ("NA", occasional dates).

**Ten-member Court.** Cases in the 1863–1864 terms can have 10 justice rows.

## Updating to a new release

1. Download the new citation-organized CSVs (case- and justice-centered) for the
   Modern release, and the Legacy files if a new Legacy release exists.
2. Put all four in one folder and run
   `python scripts/build_combined.py --src <folder>` (picks the highest-numbered
   release of each kind; rewrites data/ and regenerates justices.csv and
   natural_courts.csv).
3. If a new codebook PDF is released, run
   `python scripts/parse_codebook.py <codebook.pdf>` (needs `pdftotext`), then
   rebuild so the derived tables pick up new labels.
4. Re-check this file's quirks (e.g. whether undocumented codes got labels) and
   update the release table above and the SKILL.md header.
