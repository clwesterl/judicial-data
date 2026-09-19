#!/usr/bin/env python3
"""
scdb.py -- load, label, and search the combined Supreme Court Database (1791-present).

As a library (add the skill's scripts/ dir to sys.path first):
    import sys; sys.path.insert(0, "<skill_dir>/scripts")
    import scdb
    cases = scdb.load("case")                 # 1 row per case (citation), typed
    votes = scdb.load("justice")              # 1 row per justice per case
    cases = scdb.label(cases, ["issueArea", "decisionDirection"])   # adds *_label cols
    scdb.labels("issueArea")                  # {1: 'Criminal Procedure', ...}
    scdb.find(cases, "384 U.S. 436")          # by U.S./S.Ct./L.Ed./LEXIS cite, caseId, docket, or name
    scdb.manifest(); scdb.citation()          # provenance + how to cite the releases
    scdb.formally_decided(cases)              # decisionType in {1,6,7} (default sample)
    scdb.merits_votes(votes)                  # vote in {1..5}
    scdb.agreement(votes_subset, names)       # pairwise agreement matrix
    scdb.best_cite(cases)                     # first available reporter cite

As a CLI:
    python scdb.py info                       # releases, row counts, term coverage
    python scdb.py find miranda               # search by name / cite / docket / caseId
    python scdb.py case 1965-146              # full labeled record + every justice's vote
    python scdb.py labels issueArea           # code -> label table for one variable
    python scdb.py justice scalia             # service dates & counts for a justice
    python scdb.py cite                       # citation strings for the releases in use

Typing done by load(): coded variables -> pandas nullable Int64 (blank -> <NA>);
dateDecision/dateArgument/dateRearg -> datetime64; IDs, citations, names, docket,
chief, justiceName, lawMinor stay strings. By default the justice file drops the
25 Legacy placeholder rows (justice == -99; equally divided cases with no recorded
votes) -- pass keep_placeholders=True to retain them.
"""
import csv, json, os, re, sys
import pandas as pd

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(SKILL_DIR, "data")
REF = os.path.join(SKILL_DIR, "references")
FILES = {"case": "case_citation.csv.gz", "justice": "justice_citation.csv.gz"}

TEXT_COLS = {"caseId", "docketId", "caseIssuesId", "voteId", "usCite", "sctCite", "ledCite",
             "lexisCite", "chief", "docket", "caseName", "lawMinor", "justiceName"}
DATE_COLS = ["dateDecision", "dateArgument", "dateRearg"]
JUSTICE_VARS = {"justice", "majOpinWriter", "majOpinAssigner", "firstAgreement", "secondAgreement"}

_labels_cache = None


def _read_labels():
    global _labels_cache
    if _labels_cache is None:
        out = {}
        with open(os.path.join(REF, "value_labels.csv"), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out.setdefault(r["variable"], {})[int(r["code"])] = r["label"]
        _labels_cache = out
    return _labels_cache


def labels(variable):
    """code -> label dict for a coded variable (e.g. 'issue', 'petitioner', 'vote')."""
    lab = _read_labels()
    if variable not in lab:
        raise KeyError(f"no value labels for {variable!r}; labeled variables: {sorted(lab)}")
    return dict(lab[variable])


def load(level="case", parse=True, keep_placeholders=False, label_vars=None):
    """Load the combined data. level: 'case' or 'justice'."""
    if level not in FILES:
        raise ValueError("level must be 'case' or 'justice'")
    df = pd.read_csv(os.path.join(DATA, FILES[level]), dtype=str, keep_default_na=False)
    if level == "justice" and not keep_placeholders:
        df = df[df["justice"] != "-99"].reset_index(drop=True)
    if parse:
        for c in df.columns:
            if c in TEXT_COLS:
                continue
            if c in DATE_COLS:
                df[c] = pd.to_datetime(df[c].replace("", None), format="%m/%d/%Y")
            else:
                df[c] = pd.to_numeric(df[c].replace("", None)).astype("Int64")
    if label_vars:
        df = label(df, label_vars)
    return df


def label(df, variables=None):
    """Add '<var>_label' columns. variables=None labels every labeled column present."""
    lab = _read_labels()
    if variables is None:
        variables = [c for c in df.columns if c in lab]
    elif isinstance(variables, str):
        variables = [variables]
    df = df.copy()
    for v in variables:
        m = lab[v]
        codes = pd.to_numeric(df[v].replace("", None) if df[v].dtype == object else df[v],
                              errors="coerce")
        df[f"{v}_label"] = codes.map(lambda x: m.get(int(x)) if pd.notna(x) else None)
    return df


# ---------------------------------------------------------------- common sample helpers
FORMALLY_DECIDED = (1, 6, 7)      # signed opinion, argued per curiam, judgment of the Court
MERITS_VOTES = (1, 2, 3, 4, 5)    # excludes 6 cert-denial dissent, 7 jurisdictional dissent, 8 equally divided


def formally_decided(df, include_equally_divided=False):
    """Orally argued, formally decided cases (the usual default sample)."""
    types = FORMALLY_DECIDED + ((5,) if include_equally_divided else ())
    return df[df["decisionType"].isin(types)]


def merits_votes(v):
    """Justice rows that are participating merits votes (vote in 1-5)."""
    return v[v["vote"].isin(MERITS_VOTES)]


def best_cite(df):
    """First available cite: U.S., then S. Ct., L. Ed., LEXIS (recent cases often lack U.S.)."""
    out = df["usCite"].copy()
    for c in ("sctCite", "ledCite", "lexisCite"):
        out = out.where(out.fillna("") != "", df[c])
    return out


def agreement(v, justices=None, on="majority", return_n=False):
    """Pairwise agreement among justices over cases where both have a non-missing `on` value.
    v: justice-level rows already filtered to the sample (e.g. merits_votes of non-unanimous cases).
    justices: list of justiceName values (default: all present, in seniority-id order).
    Returns a DataFrame of agreement rates (and joint-case counts if return_n=True)."""
    if justices is None:
        justices = (v.drop_duplicates("justiceName").sort_values("justice")["justiceName"].tolist())
    w = (v[v.justiceName.isin(justices)]
         .pivot_table(index="caseId", columns="justiceName", values=on, aggfunc="first"))
    rate = pd.DataFrame(index=justices, columns=justices, dtype=float)
    n = pd.DataFrame(index=justices, columns=justices, dtype="Int64")
    for a in justices:
        for b in justices:
            both = w[a].notna() & w[b].notna() if a in w and b in w else pd.Series(False)
            n.loc[a, b] = int(both.sum())
            rate.loc[a, b] = (w.loc[both, a] == w.loc[both, b]).mean() if both.any() else float("nan")
    return (rate, n) if return_n else rate


def _norm(s):
    """lowercase, straighten curly quotes (modern case names use them)."""
    return (str(s).replace("\u2019", "'").replace("\u2018", "'")
            .replace("\u201c", '"').replace("\u201d", '"').lower())


def _citekey(s):
    return re.sub(r"[\s.]", "", str(s)).lower()


def find(df, query, limit=50):
    """Find cases by cite (any reporter), caseId, docket number, or case-name substring."""
    q = str(query).strip()
    if re.fullmatch(r"\d{4}-\d{3}", q):
        return df[df["caseId"] == q]
    key = _citekey(q)
    hit = pd.Series(False, index=df.index)
    for c in ("usCite", "sctCite", "ledCite", "lexisCite"):
        hit |= df[c].map(_citekey) == key
    if hit.any():
        return df[hit]
    hit = df["docket"].astype(str).str.lower() == q.lower()
    if hit.any():
        return df[hit]
    hit = df["caseName"].map(_norm).str.contains(_norm(q), regex=False)
    return df[hit].head(limit)


def manifest():
    with open(os.path.join(DATA, "MANIFEST.json"), encoding="utf-8") as f:
        return json.load(f)


# Legacy releases are cited by release year; add new ones here when they appear.
LEGACY_RELEASE_YEAR = {"01": 2016, "04": 2017, "07": 2021}
AUTHORS = ("Harold J. Spaeth, Lee Epstein, Michael J. Nelson, Andrew D. Martin, Jeffrey A. Segal, "
           "Theodore J. Ruger, and Sara C. Benesh")


def citation():
    """SCDB's requested citation (Penn State 'Cite Us' format), one per release in the data."""
    out = []
    for r in manifest()["releases"]:
        if r.startswith("Legacy"):
            n = r.split("_")[1]
            yr = LEGACY_RELEASE_YEAR.get(n)
            ver = f"Version {yr} Legacy Release {n}" if yr else f"Legacy Release {n} [add release year]"
            out.append(f"{AUTHORS}. {yr or 'YYYY'}. Supreme Court Database, {ver}. URL: https://scdb.psu.edu")
        else:
            yr, rel = r.split("_")
            out.append(f"{AUTHORS}. {yr}. Supreme Court Database, Version {yr} Release {rel}. "
                       f"URL: https://scdb.psu.edu")
    return out


# ---------------------------------------------------------------- CLI
CASE_FIELDS = ["caseName", "usCite", "sctCite", "ledCite", "lexisCite", "docket", "term",
               "dateArgument", "dateRearg", "dateDecision", "chief", "naturalCourt", "petitioner",
               "petitionerState", "respondent", "respondentState", "jurisdiction", "certReason",
               "adminAction", "caseOrigin", "caseSource", "lcDisagreement", "lcDisposition",
               "lcDispositionDirection", "issue", "issueArea", "decisionDirection",
               "decisionDirectionDissent", "lawType", "lawSupp", "lawMinor", "authorityDecision1",
               "authorityDecision2", "decisionType", "caseDisposition", "caseDispositionUnusual",
               "partyWinning", "declarationUncon", "precedentAlteration", "voteUnclear",
               "majOpinWriter", "majOpinAssigner", "majVotes", "minVotes"]


def _fmt(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return ""
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    return str(v)


VOTE_SHORT = {1: "majority", 2: "dissent", 3: "concur (regular)", 4: "concur (judgment only)",
              5: "judgment of the Court", 6: "dissent from cert denial", 7: "jurisdictional dissent",
              8: "equally divided"}


def _cli_case(cid):
    lab = _read_labels()
    cases = load("case")
    row = cases[cases.caseId == cid]
    if row.empty and re.fullmatch(r"\d{4}-\d{3}", cid):
        v = load("justice", keep_placeholders=True)
        v = v[v.caseId == cid]
        if len(v):
            r = v.iloc[0]
            print(f"{cid}  {r.caseName}\n  (justice-file placeholder only: no case-centered record, "
                  f"no recorded votes)\n  {r.usCite}  decided {_fmt(r.dateDecision)}  decisionType "
                  f"{_fmt(r.decisionType)} = {lab['decisionType'].get(int(r.decisionType), '')}")
            return
    if row.empty:
        hits = find(cases, cid)
        if len(hits) != 1:
            print(f"{len(hits)} matches; use a caseId."); _print_hits(hits); return
        row = hits
    r = row.iloc[0]
    cid = r.caseId
    print(f"{cid}  {r.caseName}")
    for f in CASE_FIELDS:
        v = r[f]
        s = _fmt(v)
        if s and f in lab and f != "term":
            s = f"{s} = {lab[f].get(int(v), '(undocumented code)')}"
        if s:
            print(f"  {f:26s} {s}")
    v = load("justice", keep_placeholders=True)
    v = v[v.caseId == cid]
    if len(v):
        jl = lab["justice"]
        print("\n  justice          vote                        opinion  direction  majority  joins")
        for _, x in v.iterrows():
            vote = VOTE_SHORT.get(int(x.vote), "") if pd.notna(x.vote) else "(did not participate)"
            op = {1: "", 2: "wrote", 3: "co-auth"}.get(int(x.opinion), "") if pd.notna(x.opinion) else ""
            d = {1: "cons", 2: "lib"}.get(int(x.direction), "") if pd.notna(x.direction) else ""
            m = {1: "dissent", 2: "majority"}.get(int(x.majority), "") if pd.notna(x.majority) else ""
            joins = " ".join(jl.get(int(a), str(a)) for a in (x.firstAgreement, x.secondAgreement)
                             if pd.notna(a) and int(a) > 0)
            print(f"  {x.justiceName:15s}  {vote:26s}  {op:7s}  {d:9s}  {m:8s}  {joins}")


def _print_hits(h):
    h = h.assign(cite=best_cite(h), decided=h["dateDecision"])
    cols = ["caseId", "cite", "decided", "majVotes", "minVotes", "caseName"]
    with pd.option_context("display.width", 200, "display.max_colwidth", 80):
        print(h[cols].to_string(index=False))


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return
    cmd, arg = argv[0], " ".join(argv[1:])
    if cmd == "info":
        m = manifest()
        print(f"releases: {', '.join(m['releases'])}   built: {m['built']}")
        for k in ("case", "justice"):
            print(f"  {k:8s} {m[k]['file']:26s} rows={m[k]['rows']:>7,}  cases={m[k]['cases']:,}  "
                  f"terms {m[k]['terms'][0]}-{m[k]['terms'][1]}")
    elif cmd == "find":
        _print_hits(find(load("case"), arg))
    elif cmd == "case":
        _cli_case(arg)
    elif cmd == "cite":
        print("\n".join(citation()))
    elif cmd == "labels":
        for k, v in labels(arg).items():
            print(f"{k:>8}  {v}")
    elif cmd == "justice":
        j = pd.read_csv(os.path.join(REF, "justices.csv"))
        hit = j[j.justiceName.str.lower().str.contains(arg.lower()) | (j.justice.astype(str) == arg)]
        print(hit.to_string(index=False))
    else:
        print(f"unknown command {cmd!r}\n"); print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
