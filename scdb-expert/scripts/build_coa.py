#!/usr/bin/env python3
"""Rebuild data/coa/ from a slice of the Comprehensive Court of Appeals Database.

Produces the bundled CoA case index and the CCAD <-> SCDB crosswalk.

Neither database carries the other's citation, so cases are linked on three
signals:

  1. circuit            SCDB caseSource -> CCAD circuit numbering
  2. party names        TF-IDF cosine, scored per party and order-insensitive,
                        because the CoA loser is usually the SCOTUS petitioner
  3. time to review     log-normal prior on (SCOTUS date - CoA date), calibrated
                        on confirmed links: median 441 days, 95th pct 745

A link is reported as `mutual` when the CoA case is the SCDB case's best
candidate *and* vice versa. Mutual links are the ones to trust.

Validation uses songer_gt_supct == 1, which flags Songer-sampled CoA cases the
Supreme Court later reviewed (Phase 2, CoA decisions 1952-1988). Note that
songer_gt_supct == 0 is NOT a reliable negative -- see the --validate output.

The CCAD ships as a 5.85 GB uncompressed RData file (512,263 rows x 809 columns),
too large to bundle or to read without R. Extract a slice first with the companion
R script, then point this at the result:

    Rscript scripts/coa_slice.R                      # on a machine with R + the RData
    python scripts/build_coa.py --coa coa_link.csv.gz

See references/coa.md for the matching design, the validation results, and the
code-scheme differences between the two databases.
"""
import argparse, gzip, hashlib, json, os, re, sys
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer

# SCDB caseSource -> CCAD circuit numbering (0 = D.C., 1-11, 12 = Federal)
CASESOURCE_TO_CIRCUIT = {
    21: 1, 22: 2, 23: 3, 24: 4, 25: 5, 26: 6, 27: 7, 28: 8, 29: 9,
    30: 10, 31: 11, 32: 0, 8: 12,
}

# Time-to-review prior, fitted on confirmed links (lognormal on days).
# Confirmed links: median 441 days, 5th pct 237, 95th pct 745, max 2186.
# The prior is deliberately floored: fast reviews are real (Leyra v. Denno took
# 189 days) and name evidence should not be erased by an unusual gap.
GAP_LOG_MU, GAP_LOG_SIGMA = 6.07, 0.36
GAP_MIN_DAYS, GAP_MAX_DAYS = 30, 2600
GAP_FLOOR = 0.60          # weight never falls below this; 0 = old crushing behaviour

# Federal Reporter abbreviations -> the word SCDB spells out.
ABBREV = {
    "ry": "railway", "rys": "railway", "r": "railroad", "rr": "railroad",
    "ins": "insurance", "assur": "assurance", "indem": "indemnity",
    "cas": "casualty", "mut": "mutual", "mfg": "manufacturing",
    "mach": "machine", "co": "company", "cos": "company", "coop": "cooperative",
    "corp": "corporation", "inc": "incorporated", "ltd": "limited",
    "bros": "brothers", "nat": "national", "natl": "national",
    "intl": "international", "int": "international", "am": "american",
    "assn": "association", "assoc": "association", "soc": "society",
    "bd": "board", "comm": "commission", "commn": "commission",
    "commr": "commissioner", "comrs": "commissioner", "commrs": "commissioner",
    "dept": "department", "dist": "district", "div": "division",
    "sav": "savings", "bk": "bank", "tr": "trust", "const": "construction",
    "constr": "construction", "dev": "development", "eng": "engineering",
    "equip": "equipment", "elec": "electric", "prod": "products",
    "prods": "products", "indus": "industries", "serv": "service",
    "servs": "service", "sys": "system", "transp": "transportation",
    "ss": "steamship", "pet": "petroleum", "chem": "chemical",
    "pharm": "pharmaceutical", "sec": "securities", "secs": "securities",
    "invest": "investment", "mtg": "mortgage", "fin": "finance",
    "util": "utilities", "tel": "telephone", "pub": "public",
    "publg": "publishing", "bldg": "building", "hosp": "hospital",
    "univ": "university", "govt": "government", "fed": "federal",
    "us": "unitedstates", "usa": "unitedstates", "nlrb": "nlrb",
    "lines": "line", "stores": "store", "mills": "mill", "works": "work",
}
STOP = {
    "v", "vs", "et", "al", "ux", "vir", "ano", "and", "the", "of", "a", "an",
    "in", "on", "for", "by", "to", "ex", "rel", "dba", "aka", "fka", "jr",
    "sr", "ii", "iii", "iv", "etc", "d", "b", "individually", "behalf",
    "its", "his", "her", "their", "all", "others", "similarly", "situated",
    "appellant", "appellants", "appellee", "appellees", "petitioner",
    "petitioners", "respondent", "respondents", "plaintiff", "plaintiffs",
    "defendant", "defendants", "successor", "trading", "doing", "business",
    "unknown", "none", "unnamed", "unspecified", "na", "nan",
}
PUNCT = re.compile(r"[^a-z0-9]+")
SPLIT_V = re.compile(r"\s+v+s?\.?\s+")


def normalize(text):
    """Party name -> space-joined 4-char stems, abbreviations expanded."""
    if not isinstance(text, str) or not text.strip():
        return ""
    s = text.lower().replace("&", " and ")
    s = s.replace("u. s.", " us ").replace("u.s.", " us ")
    out = []
    for tok in PUNCT.split(s):
        if not tok or tok in STOP:
            continue
        tok = ABBREV.get(tok, tok)
        if tok in STOP:
            continue
        out.append(tok[:4] if len(tok) > 4 else tok)
    return " ".join(out)


def split_case_name(name):
    """SCDB caseName -> (first side, second side); ('', whole) when there's no 'v.'"""
    if not isinstance(name, str):
        return "", ""
    parts = SPLIT_V.split(name, maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else ("", name)


def gap_z(days):
    """Signed standard deviations of log time-to-review from the typical gap."""
    d = np.asarray(days, dtype=float)
    z = np.full(d.shape, np.inf)
    ok = d > 0
    z[ok] = (np.log(d[ok]) - GAP_LOG_MU) / GAP_LOG_SIGMA
    return z


def gap_weight(days, floor=GAP_FLOOR):
    """Mild, floored date prior: in [floor, 1]. Downweights implausible gaps
    without letting the date override an exact party-name match."""
    z = gap_z(days)
    w = np.exp(-0.5 * np.minimum(z * z, 50.0))
    return floor + (1.0 - floor) * w


SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_scdb(skill_dir=SKILL_DIR):
    sys.path.insert(0, os.path.join(skill_dir, "scripts"))
    import scdb
    c = scdb.load("case")
    keep = ["caseId", "caseName", "usCite", "lexisCite", "docket", "term",
            "dateDecision", "caseSource", "caseOrigin", "decisionType",
            "partyWinning", "lcDisposition", "issueArea", "decisionDirection"]
    c = c[[k for k in keep if k in c.columns]].copy()
    c["coa_circuit"] = c.caseSource.map(CASESOURCE_TO_CIRCUIT)
    c = c[c.coa_circuit.notna() & c.dateDecision.notna()].copy()
    c["coa_circuit"] = c.coa_circuit.astype(int)
    sides = c.caseName.map(split_case_name)
    c["p1"] = [normalize(a) for a, _ in sides]
    c["p2"] = [normalize(b) for _, b in sides]
    c["pooled"] = (c.p1 + " " + c.p2).str.strip()
    return c.reset_index(drop=True)


def load_coa(path):
    cols = ["caseid", "citation", "circuit", "year", "decision_date", "docket_number",
            "is_enbanc", "judge_count", "scdb_first_appellant_name",
            "scdb_first_respondent_name", "scdb_first_disposition",
            "scdb_first_broad_area", "scdb_first_direction_oneshot",
            "songer_present", "songer_gt_supct"]
    d = pd.read_csv(path, dtype={"caseid": str}, low_memory=False, usecols=cols)
    d = d[d.circuit.notna()].copy()
    d["circuit"] = d.circuit.astype(int)
    d["decision_date"] = pd.to_datetime(d.decision_date, errors="coerce")
    d = d[d.decision_date.notna()].copy()
    d["p1"] = d.scdb_first_appellant_name.map(normalize)
    d["p2"] = d.scdb_first_respondent_name.map(normalize)
    d["pooled"] = (d.p1 + " " + d.p2).str.strip()
    return d.reset_index(drop=True)


def build_links(scdb_df, coa_df, w_pair=0.75, topk=3, gap_floor=GAP_FLOOR):
    """Score every (SCDB case, in-window CoA case) pair; keep top-k per SCDB case
    and the single best SCDB case per CoA case."""
    vec = TfidfVectorizer(analyzer="word", token_pattern=r"\S+", sublinear_tf=True)
    vec.fit(pd.concat([coa_df.pooled, coa_df.p1, coa_df.p2,
                       scdb_df.pooled, scdb_df.p1, scdb_df.p2]))

    best_for_coa = np.zeros(len(coa_df))
    best_scdb_for_coa = np.full(len(coa_df), -1, dtype=np.int64)
    rows = []
    scdb_ids = scdb_df.caseId.values

    for circ in sorted(scdb_df.coa_circuit.unique()):
        s = scdb_df[scdb_df.coa_circuit == circ]
        pool = coa_df[coa_df.circuit == circ].sort_values("decision_date")
        if s.empty or pool.empty:
            continue
        sidx = s.index.values                          # global SCDB row ids
        gidx = pool.index.values                       # global CoA row ids
        A = sparse.csr_matrix(vec.transform(pool.p1))
        R = sparse.csr_matrix(vec.transform(pool.p2))
        O = sparse.csr_matrix(vec.transform(pool.pooled))
        dates = pool.decision_date.values.astype("datetime64[D]")
        S1 = sparse.csr_matrix(vec.transform(s.p1))
        S2 = sparse.csr_matrix(vec.transform(s.p2))
        SO = sparse.csr_matrix(vec.transform(s.pooled))
        sd = s.dateDecision.values.astype("datetime64[D]")
        lo = np.searchsorted(dates, sd - np.timedelta64(GAP_MAX_DAYS, "D"), "left")
        hi = np.searchsorted(dates, sd - np.timedelta64(GAP_MIN_DAYS, "D"), "right")

        for i in range(len(s)):
            a, b = lo[i], hi[i]
            rec = {"caseId": s.caseId.iloc[i], "caseName": s.caseName.iloc[i],
                   "usCite": s.usCite.iloc[i], "term": s.term.iloc[i],
                   "scotus_date": s.dateDecision.iloc[i], "circuit": circ,
                   "n_candidates": int(b - a), "_scdb_row": int(sidx[i])}
            if b <= a:
                rows.append(rec)
                continue
            s11 = (S1[i] @ A[a:b].T).toarray().ravel()
            s22 = (S2[i] @ R[a:b].T).toarray().ravel()
            s12 = (S1[i] @ R[a:b].T).toarray().ravel()
            s21 = (S2[i] @ A[a:b].T).toarray().ravel()
            pooled = (SO[i] @ O[a:b].T).toarray().ravel()
            pair = np.maximum(np.sqrt(s11 * s22), np.sqrt(s12 * s21))
            gaps = (sd[i] - dates[a:b]).astype("timedelta64[D]").astype(float)
            name = w_pair * pair + (1 - w_pair) * pooled
            score = name * gap_weight(gaps, gap_floor)

            # per-CoA running best (the reverse direction of the match)
            win = gidx[a:b]
            better = score > best_for_coa[win]
            best_for_coa[win[better]] = score[better]
            best_scdb_for_coa[win[better]] = sidx[i]

            order = np.argsort(-score)[:topk]
            for r, j in enumerate(order, 1):
                sfx = "" if r == 1 else str(r)
                rec[f"coa_caseid{sfx}"] = pool.caseid.iloc[j + a]
                rec[f"score{sfx}"] = round(float(score[j]), 4)
                if r == 1:
                    rec.update(
                        coa_citation=pool.citation.iloc[j + a],
                        coa_date=pool.decision_date.iloc[j + a],
                        gap_days=int(gaps[j]),
                        gap_z=round(float(gap_z(gaps[j:j + 1])[0]), 2),
                        name_score=round(float(name[j]), 4),
                        pair_score=round(float(pair[j]), 4),
                        pooled_score=round(float(pooled[j]), 4),
                        coa_songer_gt_supct=pool.songer_gt_supct.iloc[j + a],
                        coa_disposition=pool.scdb_first_disposition.iloc[j + a],
                        coa_is_enbanc=pool.is_enbanc.iloc[j + a],
                        lcDisposition=s.lcDisposition.iloc[i],
                        _coa_row=int(gidx[j + a]),
                    )
            rec["margin"] = round(rec["score"] - rec.get("score2", 0.0), 4)
            rows.append(rec)

    x = pd.DataFrame(rows)
    # Mutual best match: this SCDB case is also the CoA case's own best SCDB case.
    # (set below, then used by assign_confidence)
    x["mutual"] = False
    have = x._coa_row.notna()
    rr = x.loc[have, "_coa_row"].astype(int).values
    x.loc[have, "mutual"] = best_scdb_for_coa[rr] == x.loc[have, "_scdb_row"].values
    x["coa_best_scdb"] = pd.NA
    x.loc[have, "coa_best_scdb"] = [
        scdb_ids[j] if j >= 0 else pd.NA for j in best_scdb_for_coa[rr]
    ]
    return x, best_for_coa, best_scdb_for_coa


def assign_confidence(x):
    """Tier each link. Calibrated on CoA decisions 1952-1988 against
    songer_gt_supct: false-positive rate ~1.2% in tier A, ~1.8% in A+B."""
    s, mu = x.score.fillna(0), x.mutual.fillna(False)
    tier = pd.Series("none", index=x.index)
    tier[(s >= 0.20)] = "C"
    tier[mu & (s >= 0.35)] = "B"
    tier[mu & (s >= 0.50)] = "A"
    return tier


def write_gz(df, path):
    """Deterministic gzip (mtime 0) so rebuilds are byte-identical."""
    with gzip.GzipFile(path, "wb", mtime=0) as g:
        df.to_csv(g, index=False)
    h = hashlib.sha256(open(path, "rb").read()).hexdigest()
    return {"rows": int(len(df)), "cols": int(df.shape[1]), "sha256": h,
            "bytes": os.path.getsize(path)}


CASE_COLS = ["caseid", "citation", "circuit", "year", "decision_date", "docket_number",
             "judge_count", "is_enbanc", "is_percuriam", "n_opinions", "n_majority",
             "n_concurrence", "n_dissent", "author", "all_judges_matched",
             "all_authors_matched", "scdb_first_appellant_name",
             "scdb_first_appellant_category", "scdb_first_respondent_name",
             "scdb_first_respondent_category", "scdb_first_disposition",
             "scdb_first_appellant_win", "scdb_first_broad_area", "scdb_second_sub_area",
             "scdb_first_direction_oneshot", "songer_present", "songer_gt_supct",
             "idb_present"]
LINK_COLS = ["caseId", "caseName", "usCite", "term", "scotus_date", "circuit",
             "coa_caseid", "coa_citation", "coa_date", "gap_days", "gap_z", "score",
             "name_score", "margin", "mutual", "n_candidates", "confidence"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coa", default="coa_link.csv.gz",
                    help="output of scripts/coa_slice.R")
    ap.add_argument("--skill-dir", default=SKILL_DIR)
    ap.add_argument("--gap-floor", type=float, default=GAP_FLOOR,
                    help="floor on the date prior; 1.0 disables it entirely")
    ap.add_argument("--w-pair", type=float, default=0.75,
                    help="weight on per-party similarity vs pooled-bag similarity")
    a = ap.parse_args()

    out_dir = os.path.join(a.skill_dir, "data", "coa")
    os.makedirs(out_dir, exist_ok=True)

    scdb_df = load_scdb(a.skill_dir)
    coa_df = load_coa(a.coa)
    print(f"SCDB cases from a numbered circuit: {len(scdb_df):,}")
    print(f"CoA cases with a circuit and date:  {len(coa_df):,}")

    x, best, who = build_links(scdb_df, coa_df, w_pair=a.w_pair, gap_floor=a.gap_floor)
    x["confidence"] = assign_confidence(x)

    raw = pd.read_csv(a.coa, dtype={"caseid": str}, low_memory=False,
                      usecols=lambda c: c in CASE_COLS)[CASE_COLS]
    for c in raw.columns:
        if raw[c].dtype.kind == "f" and raw[c].dropna().mod(1).eq(0).all():
            raw[c] = raw[c].astype("Int64")
    raw = raw.sort_values(["year", "circuit", "caseid"], kind="stable")
    cases_meta = write_gz(raw, os.path.join(out_dir, "coa_cases.csv.gz"))

    link = x.loc[x.confidence.isin(["A", "B", "C"]), LINK_COLS].copy()
    link["coa_caseid"] = link.coa_caseid.astype("Int64").astype(str)
    link = link.sort_values(["term", "caseId"], kind="stable")
    link_meta = write_gz(link, os.path.join(out_dir, "crosswalk.csv.gz"))

    tiers = link.confidence.value_counts().to_dict()
    json.dump({
        "source": "Comprehensive Court of Appeals Database, Release 09-2026 "
                  "(Sapiro-Gheiler and Kastellec, Princeton University)",
        "source_rows": 512263, "source_cols": 809,
        "coa_cases.csv.gz": cases_meta, "crosswalk.csv.gz": link_meta,
        "crosswalk_tiers": {k: int(v) for k, v in tiers.items()},
        "matcher": {"gap_floor": a.gap_floor, "w_pair": a.w_pair,
                    "gap_log_mu": GAP_LOG_MU, "gap_log_sigma": GAP_LOG_SIGMA,
                    "gap_window_days": [GAP_MIN_DAYS, GAP_MAX_DAYS]},
    }, open(os.path.join(out_dir, "MANIFEST.json"), "w"), indent=2)

    print(f"wrote {out_dir}/coa_cases.csv.gz  ({cases_meta['rows']:,} rows)")
    print(f"wrote {out_dir}/crosswalk.csv.gz  ({link_meta['rows']:,} rows)")
    print(link.confidence.value_counts().reindex(["A", "B", "C"]).to_string())


if __name__ == "__main__":
    main()
