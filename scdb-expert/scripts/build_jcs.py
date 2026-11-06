#!/usr/bin/env python3
"""
Build the skill's Judicial Common Space (JCS) files from the raw JCS release.

Usage:
    python build_jcs.py --src DIR_WITH_RAW_JCS [--out DATA_DIR/jcs]

Expected raw files (R write.csv exports; first column is an unnamed row index):
    jcs_supreme_court_YYYY_long.csv   term, justiceName, jcs      (one row per justice-term)
    jcs_supreme_court_YYYY_wide.csv   justiceName, jcsTTTT ...   (same values, wide; used only as a check)
    coa_judges_YYYY.csv               name, circuit, jcs          (one row per judge-circuit)
    jcs_medians.csv                   year, term, congress, president, house/senate/sc medians,
                                      circuit_median1-13, circuit_sd1-13

Outputs (default: <skill>/data/jcs/):
    jcs_justice_term.csv   term, justice (SCDB id), justiceName, jcs
    jcs_coa_judges.csv     judge_key, name, last_name, first_middle, suffix, circuit,
                           circuit_name, scdb_caseSource, scdb_justice (if later a justice), jcs
    jcs_medians.csv        raw medians table, row-index column dropped
    circuits.csv           JCS circuit number -> name -> SCDB caseSource code
    MANIFEST.json          source files, checksums, row counts, checks

Changes to values: none, except rounding to 6 decimals. The raw values were stored
as single-precision floats (e.g. 0.395999997854233 for 0.396); 6 decimals is below
float32 resolution for |x| < 1, so rounding removes only storage noise.
"""
import argparse, datetime, glob, hashlib, json, os, re, sys, unicodedata
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(SKILL, "data", "jcs")

# JCS circuit numbering: 1-11 regional, 12 = D.C. Circuit, 13 = Federal Circuit
CIRCUITS = [(i, f"{n} Circuit", 20 + i) for i, n in enumerate(
    ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth",
     "Ninth", "Tenth", "Eleventh"], start=1)]
CIRCUITS += [(12, "D.C. Circuit", 32), (13, "Federal Circuit", 8)]
SUFFIXES = {"Jr.", "Sr.", "I", "II", "III", "IV"}
# Appeals judges later elevated to the Supreme Court -> SCDB justiceName. Hand-verified:
# surname+initial matching also hits Thomas A. Clark (not Tom C. Clark), Shackelford Miller
# (not Samuel F. Miller), and J.M. Harlan I, so the list is explicit.
ELEVATED = {
    "alito_samuel_a_jr": "SAAlito", "blackmun_harry_andrew": "HABlackmun", "breyer_stephen_g": "SGBreyer",
    "burger_warren_earl": "WEBurger", "ginsburg_ruth_bader": "RBGinsburg", "gorsuch_neil": "NMGorsuch",
    "harlan_john_marshall": "JHarlan2", "jackson_ketanji_brown": "KBJackson", "kavanaugh_brett": "BMKavanaugh",
    "kennedy_anthony_mccleod": "AMKennedy", "marshall_thurgood": "TMarshall", "minton_sherman": "SMinton",
    "roberts_john": "JGRoberts", "scalia_antonin": "AScalia", "sotomayor_sonia": "SSotomayor",
    "souter_david_h": "DHSouter", "stevens_john_paul": "JPStevens", "stewart_potter": "PStewart",
    "thomas_clarence": "CThomas", "vinson_frederic_moore": "FMVinson", "whittaker_charles_evans": "CEWhittaker",
}


def sha256(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def one(src, pattern):
    hits = sorted(glob.glob(os.path.join(src, pattern)))
    if not hits:
        sys.exit(f"no file matching {pattern} in {src}")
    return hits[-1]


def read_r_csv(path):
    df = pd.read_csv(path, na_values=["NA"], encoding="utf-8")
    first = df.columns[0]
    if first in ("", "Unnamed: 0"):
        df = df.drop(columns=first)
    return df


def parse_name(name):
    parts = [p.strip() for p in name.split(",")]
    last, rest = parts[0], parts[1:]
    suffix = rest[-1] if len(rest) > 1 and rest[-1] in SUFFIXES else ""
    if suffix:
        rest = rest[:-1]
    return last, " ".join(rest), suffix


def key(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", default=DEFAULT_OUT)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    checks = {}

    # --- Supreme Court justice-term scores, linked to SCDB justice ids
    lp, wp = one(a.src, "jcs_supreme_court_*_long.csv"), one(a.src, "jcs_supreme_court_*_wide.csv")
    L, W = read_r_csv(lp), read_r_csv(wp)
    wl = W.melt(id_vars="justiceName", var_name="t", value_name="jcs").dropna()
    wl["term"] = wl.t.str.replace("jcs", "").astype(int)
    m = L.merge(wl[["justiceName", "term", "jcs"]], on=["justiceName", "term"], how="outer",
                suffixes=("", "_w"), indicator=True)
    checks["long_equals_wide"] = bool((m._merge == "both").all() and (m.jcs - m.jcs_w).abs().max() == 0)
    js = pd.read_csv(os.path.join(SKILL, "references", "justices.csv"))
    L = L.merge(js[["justice", "justiceName"]], on="justiceName", how="left", validate="many_to_one")
    checks["justices_unmatched_to_scdb"] = sorted(L.justiceName[L.justice.isna()].unique().tolist())
    assert not L.duplicated(["term", "justiceName"]).any()
    L["jcs"] = L.jcs.round(6)
    L = L[["term", "justice", "justiceName", "jcs"]].sort_values(["term", "justice"])
    L.to_csv(os.path.join(a.out, "jcs_justice_term.csv"), index=False)

    # --- Courts of appeals judges
    cp = one(a.src, "coa_judges_*.csv")
    C = read_r_csv(cp)
    parsed = C.name.map(parse_name)
    C["last_name"] = parsed.str[0]
    C["first_middle"] = parsed.str[1]
    C["suffix"] = parsed.str[2]
    C["judge_key"] = C.name.map(key)
    cmap = {c: (n, s) for c, n, s in CIRCUITS}
    C["circuit_name"] = C.circuit.map(lambda c: cmap[c][0])
    C["scdb_caseSource"] = C.circuit.map(lambda c: cmap[c][1])
    C["jcs"] = C.jcs.round(6)
    jid = js.set_index("justiceName").justice
    missing = [k for k in ELEVATED if k not in set(C.judge_key)]
    assert not missing, f"elevated judges not found: {missing}"
    C["scdb_justice"] = C.judge_key.map(lambda k: jid.get(ELEVATED[k]) if k in ELEVATED else None).astype("Int64")
    checks["elevated_to_scotus"] = int(C.scdb_justice.notna().sum())
    assert not C.duplicated(["judge_key", "circuit"]).any()
    multi = C[C.judge_key.duplicated(keep=False)]
    checks["judges_listed_on_two_circuits"] = int(multi.judge_key.nunique())
    checks["judges_missing_jcs"] = C.name[C.jcs.isna()].tolist()
    C = C[["judge_key", "name", "last_name", "first_middle", "suffix", "circuit", "circuit_name",
           "scdb_caseSource", "scdb_justice", "jcs"]].sort_values(["last_name", "first_middle", "circuit"])
    C.to_csv(os.path.join(a.out, "jcs_coa_judges.csv"), index=False)

    # --- Medians
    mp = one(a.src, "jcs_medians*.csv")
    M = read_r_csv(mp)
    num = [c for c in M.columns if c not in ("year", "term", "congress")]
    M[num] = M[num].round(6)
    M["term"] = M["term"].astype("Int64")
    sc = L.groupby("term").jcs.median().round(6)
    chk = M.dropna(subset=["term", "sc_median"]).set_index("term").sc_median
    checks["sc_median_equals_median_of_justice_scores"] = bool(
        ((chk - sc.reindex(chk.index)).abs() < 1e-6).all())
    checks["term_equals_year_minus_1"] = bool((M.dropna(subset=["term"]).eval("year - term") == 1).all())
    checks["duplicate_years"] = M.year[M.year.duplicated()].unique().tolist()
    M.to_csv(os.path.join(a.out, "jcs_medians.csv"), index=False)

    circ = pd.DataFrame(CIRCUITS, columns=["circuit", "circuit_name", "scdb_caseSource"])
    circ["first_year_with_median"] = [
        int(M.year[M[f"circuit_median{c}"].notna()].min()) for c in circ.circuit]
    circ.to_csv(os.path.join(a.out, "circuits.csv"), index=False)

    man = {
        "built": datetime.date.today().isoformat(),
        "builder": "scripts/build_jcs.py",
        "sources": [{"path": os.path.basename(p), "sha256": sha256(p)} for p in (lp, wp, cp, mp)],
        "justice_term": {"rows": len(L), "justices": int(L.justiceName.nunique()),
                         "terms": [int(L.term.min()), int(L.term.max())]},
        "coa_judges": {"rows": len(C), "judges": int(C.judge_key.nunique())},
        "medians": {"rows": len(M), "years": [int(M.year.min()), int(M.year.max())]},
        "checks": checks,
    }
    with open(os.path.join(a.out, "MANIFEST.json"), "w") as f:
        json.dump(man, f, indent=2)
    print(json.dumps(man, indent=2))


if __name__ == "__main__":
    main()
