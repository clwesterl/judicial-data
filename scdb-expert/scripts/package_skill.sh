#!/usr/bin/env bash
# Package the skill as a zip for upload to claude.ai (Customize -> Skills).
#
#   scripts/package_skill.sh           full,  ~43 MB  -> scdb-expert.zip
#   scripts/package_skill.sh --slim    slim,   ~7 MB  -> scdb-expert-slim.zip
#
# The slim build leaves out data/coa/coa_cases.csv.gz, which is 37 of the 43 MB
# and may exceed what a skill upload accepts. Keep that file on each machine and
# point the skill at it:
#
#   export SCDB_DATA_EXTRA=~/judicial-data/scdb-expert/data
#
# Everything else -- SCDB, JCS, the CoA<->SCDB crosswalk, all the seat tables --
# is in both builds. In Claude Code, symlinking the repo is simpler than either
# zip, because git pull then updates the skill:
#
#   ln -s "$PWD/scdb-expert" ~/.claude/skills/scdb-expert
set -euo pipefail

slim=false
if [[ -n "${1:-}" ]]; then
  if [[ "$1" == "--slim" ]]; then slim=true
  else echo "usage: $0 [--slim]" >&2; exit 2
  fi
fi

skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
repo_root="$(dirname "$skill_dir")"
name="$(basename "$skill_dir")"          # the folder name must match the skill name
if $slim; then out="$repo_root/$name-slim.zip"; else out="$repo_root/$name.zip"; fi

[[ -f "$skill_dir/SKILL.md" ]] || { echo "no SKILL.md in $skill_dir" >&2; exit 1; }

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
cp -R "$skill_dir" "$stage/$name"
find "$stage/$name" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$stage/$name" \( -name '*.pyc' -o -name '.DS_Store' \) -delete 2>/dev/null || true
if $slim; then rm -f "$stage/$name/data/coa/coa_cases.csv.gz"; fi

rm -f "$out"
(cd "$stage" && zip -q -r -9 "$out" "$name")

printf '%s  (%s)\n' "$out" "$(du -h "$out" | cut -f1)"
if $slim; then
  printf 'slim: set SCDB_DATA_EXTRA=%s on each machine\n' "$skill_dir/data"
fi
