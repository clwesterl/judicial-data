# SCDB raw release files

Unmodified files as downloaded from the Supreme Court Database (scdb.psu.edu),
gzipped (`gzip -9 -n`) to keep the repo small. These are the inputs to
`../scdb-expert/scripts/build_combined.py`.

| file | release | terms |
|---|---|---|
| SCDB_Legacy_07_caseCentered_Citation.csv.gz | Legacy 07 (Oct 1, 2021) | 1791–1945 |
| SCDB_Legacy_07_justiceCentered_Citation.csv.gz | Legacy 07 | 1791–1945 |
| SCDB_2026_01_caseCentered_Citation.csv.gz | 2026 Release 01 | 1946–2025 |
| SCDB_2026_01_justiceCentered_Citation.csv.gz | 2026 Release 01 | 1946–2025 |
| SCDB_2023_01_codebook.pdf | codebook 2023_01 | — |

Rebuild the combined files (identical output to what is committed in
`scdb-expert/data/`):

```bash
python scdb-expert/scripts/build_combined.py --src scdb-raw
```

When a new release comes out, add its files here (old ones can stay; the build
picks the highest-numbered release of each kind), rebuild, and commit.
