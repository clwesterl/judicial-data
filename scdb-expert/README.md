# scdb-expert (Claude skill)

Supreme Court Database expert with the combined data bundled
(SCDB Legacy 07 + 2026_01, citation-organized, terms 1791–2025). Claude reads
`SKILL.md`; this file is for humans.

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

The data files are ~6.4 MB gzipped, fine for GitHub.

**Using the data outside Claude:** `data/*.csv.gz` are plain gzipped CSVs;
`readr::read_csv()`, `data.table::fread()` (with R.utils), and `pandas.read_csv()`
read them directly. `scripts/scdb.R` and `scripts/scdb.py` add typing and labels.

## Update to a new SCDB release

In the judicial-data repo the original release files live in `../scdb-raw/`
(gzipped; the build reads .csv or .csv.gz).

```bash
python scripts/build_combined.py --src ../scdb-raw   # or any folder with the 4 citation CSVs
python scripts/parse_codebook.py ~/Downloads/SCDB_YYYY_RR_codebook.pdf   # only if codebook changed
```

Then update the release facts in `SKILL.md` and `references/data_notes.md`, and
re-upload / commit. Details in `references/data_notes.md`.
