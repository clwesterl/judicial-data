#!/usr/bin/env python3
"""
Combine SCDB Legacy (1791-1945) and Modern (1946-present) releases into one
case-centered file and one justice-centered file (both organized by citation).

Usage:
    python build_combined.py --src DIR_WITH_RAW_CSVS [--out DATA_DIR]

The source directory must contain the four official CSVs, e.g.
    SCDB_Legacy_07_caseCentered_Citation.csv
    SCDB_Legacy_07_justiceCentered_Citation.csv
    SCDB_2026_01_caseCentered_Citation.csv
    SCDB_2026_01_justiceCentered_Citation.csv
(gzipped copies, *.csv.gz, work too. If several releases are present, the
highest-numbered one of each kind is used.)

Outputs (default: the skill's data/ directory):
    case_citation.csv.gz      one row per case (lead docket / citation)
    justice_citation.csv.gz   one row per justice per case
    MANIFEST.json             releases, row counts, checksums, harmonization log
and two derived lookup tables in references/ (regenerated from the data):
    justices.csv              id, name, first/last term, votes, majority opinions
    natural_courts.csv        code, label, chief, date range, participating justices

Harmonization (deliberately minimal; the schema is left exactly as released):
  1. Encoding: Legacy files ship as cp1252 (a stray section sign); everything
     is re-encoded as UTF-8.
  2. Missing values: Legacy files write the literal string "NULL" in lawMinor
     (and voteId on 25 placeholder rows); Modern files leave missing fields
     blank. "NULL" is converted to blank so blank means missing everywhere.
  3. Row order: stable sort by caseId, Legacy first. Justice order within a
     case is preserved.
Nothing else is changed. Sentinel values that carry meaning (e.g. justice=-99
on placeholder rows) are kept and documented in references/data_notes.md.
"""
import argparse, datetime, glob, gzip, hashlib, io, json, os, re, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(os.path.dirname(HERE), "data")


def raw_bytes(path):
    with open(path, "rb") as f:
        b = f.read()
    return gzip.decompress(b) if path.endswith(".gz") else b


def sha256(path, decompressed=True):
    """Checksum of the CSV content (decompressed, so .csv and .csv.gz sources agree)."""
    b = raw_bytes(path) if decompressed else open(path, "rb").read()
    return hashlib.sha256(b).hexdigest()


def pick(src, era, unit):
    if era == "legacy":
        pat = os.path.join(src, f"SCDB_Legacy_*_{unit}_Citation.csv")
    else:
        pat = os.path.join(src, f"SCDB_[0-9][0-9][0-9][0-9]_*_{unit}_Citation.csv")
    hits = sorted(glob.glob(pat) + glob.glob(pat + ".gz"))
    if not hits:
        sys.exit(f"missing {era} {unit} file matching {pat}")
    return hits[-1]


def read(path):
    raw = raw_bytes(path)
    try:
        raw.decode("utf-8")
        enc = "utf-8"
    except UnicodeDecodeError:
        enc = "cp1252"
    df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, encoding=enc)
    return df, enc


def release_of(path):
    m = re.search(r"SCDB_(Legacy_\d+|\d{4}_\d+)_", os.path.basename(path))  # works for .csv.gz too
    return m.group(1) if m else os.path.basename(path)


def combine(src, out, unit):
    lp, mp = pick(src, "legacy", unit), pick(src, "modern", unit)
    L, lenc = read(lp)
    M, menc = read(mp)
    assert list(L.columns) == list(M.columns), f"{unit}: column mismatch"
    assert not (set(L.caseId) & set(M.caseId)), f"{unit}: overlapping caseIds"
    lmax, mmin = L.term.astype(int).max(), M.term.astype(int).min()
    assert lmax < mmin, f"{unit}: term ranges overlap ({lmax} vs {mmin})"
    log = []
    for name, df in (("legacy", L), ("modern", M)):
        nulls = (df == "NULL").sum()
        nulls = {k: int(v) for k, v in nulls.items() if v}
        if nulls:
            log.append({"file": name, "NULL->blank": nulls})
    C = pd.concat([L, M], ignore_index=True).replace("NULL", "")
    C = C.sort_values("caseId", kind="stable").reset_index(drop=True)
    fname = {"caseCentered": "case_citation.csv.gz",
             "justiceCentered": "justice_citation.csv.gz"}[unit]
    outp = os.path.join(out, fname)
    C.to_csv(outp, index=False, encoding="utf-8",
             compression={"method": "gzip", "compresslevel": 9, "mtime": 0})
    info = {
        "file": fname,
        "rows": len(C), "columns": len(C.columns), "cases": int(C.caseId.nunique()),
        "terms": [int(C.term.astype(int).min()), int(C.term.astype(int).max())],
        "sources": [
            {"path": os.path.basename(lp), "release": release_of(lp), "encoding": lenc,
             "rows": len(L), "terms": [int(L.term.astype(int).min()), int(lmax)], "sha256": sha256(lp)},
            {"path": os.path.basename(mp), "release": release_of(mp), "encoding": menc,
             "rows": len(M), "terms": [int(mmin), int(M.term.astype(int).max())], "sha256": sha256(mp)},
        ],
        "harmonization": log,
        "sha256": sha256(outp, decompressed=False),
    }
    return info


def derive_references(data_dir, ref_dir):
    C = pd.read_csv(os.path.join(data_dir, "case_citation.csv.gz"), dtype=str, keep_default_na=False)
    J = pd.read_csv(os.path.join(data_dir, "justice_citation.csv.gz"), dtype=str, keep_default_na=False)
    J = J[J.justice != "-99"].copy()
    J["t"] = J.term.astype(int)
    J["d"] = pd.to_datetime(J.dateDecision, format="%m/%d/%Y")
    J["jid"] = J.justice.astype(int)
    auth = C.majOpinWriter[C.majOpinWriter != ""].value_counts()
    js = (J.groupby(["jid", "justiceName"])
            .agg(first_term=("t", "min"), last_term=("t", "max"),
                 first_decision=("d", "min"), last_decision=("d", "max"),
                 cases_on_bench=("caseId", "nunique"),
                 votes_cast=("vote", lambda v: int((v != "").sum())),
                 dissents=("majority", lambda v: int((v == "1").sum())))
            .reset_index().rename(columns={"jid": "justice"}))
    js["majority_opinions"] = js.justice.astype(str).map(auth).fillna(0).astype(int)
    for c in ("first_decision", "last_decision"):
        js[c] = js[c].dt.strftime("%Y-%m-%d")
    js.sort_values("justice").to_csv(os.path.join(ref_dir, "justices.csv"), index=False)

    labs = pd.read_csv(os.path.join(ref_dir, "value_labels.csv"), dtype=str)
    nlab = labs[labs.variable == "naturalCourt"].set_index("code").label
    J["nc"] = J.naturalCourt.astype(int)
    # participants = justices who cast at least one vote in cases coded to that natural court
    members = (J[J.vote != ""].drop_duplicates(["nc", "jid"]).sort_values(["nc", "jid"])
                 .groupby("nc").justiceName.agg(" ".join))
    nc = (J.groupby("nc").agg(chief=("chief", "first"), first_term=("t", "min"), last_term=("t", "max"),
                              first_decision=("d", "min"), last_decision=("d", "max"),
                              cases=("caseId", "nunique"))
            .join(members.rename("participants")).reset_index().rename(columns={"nc": "naturalCourt"}))
    nc.insert(1, "label", nc.naturalCourt.astype(str).map(nlab))
    nc["n_participants"] = nc.participants.str.split().str.len()
    for c in ("first_decision", "last_decision"):
        nc[c] = nc[c].dt.strftime("%Y-%m-%d")
    nc.to_csv(os.path.join(ref_dir, "natural_courts.csv"), index=False)
    return len(js), len(nc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    manifest = {
        "built": datetime.date.today().isoformat(),
        "builder": "scripts/build_combined.py",
        "note": "Legacy (1791-1945) + Modern (1946-) SCDB, organized by citation. "
                "Schema identical to the official releases; see references/data_notes.md.",
        "case": combine(a.src, a.out, "caseCentered"),
        "justice": combine(a.src, a.out, "justiceCentered"),
    }
    rel = sorted({s["release"] for k in ("case", "justice") for s in manifest[k]["sources"]})
    manifest["releases"] = rel
    with open(os.path.join(a.out, "MANIFEST.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    ref_dir = os.path.join(os.path.dirname(os.path.abspath(a.out)), "references")
    if os.path.exists(os.path.join(ref_dir, "value_labels.csv")):
        nj, nn = derive_references(a.out, ref_dir)
        print(f"references: justices.csv ({nj}), natural_courts.csv ({nn})")
    print(json.dumps({k: (v if k not in ("case", "justice") else
                          {x: v[x] for x in ("file", "rows", "cases", "terms")})
                      for k, v in manifest.items()}, indent=2))


if __name__ == "__main__":
    main()
