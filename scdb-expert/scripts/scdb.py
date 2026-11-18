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
    scdb.jcs("justice"|"coa"|"medians"|"circuit_medians"|"circuits")   # Judicial Common Space
    scdb.add_jcs(votes); scdb.add_medians(cases); scdb.add_circuit_medians(cases)
    scdb.state_elections("elections"|"seats"|"retention"|"selection"|"states"|"fixes")
    scdb.state_candidates(); scdb.find_state_judge("durham"); scdb.state_selection("AZ", 1970)
    scdb.add_state_selection(cases)           # how the reviewed state court was chosen

As a CLI:
    python scdb.py info                       # releases, row counts, term coverage
    python scdb.py find miranda               # search by name / cite / docket / caseId
    python scdb.py case 1965-146              # full labeled record + every justice's vote
    python scdb.py labels issueArea           # code -> label table for one variable
    python scdb.py justice scalia             # service dates & counts for a justice
    python scdb.py cite                       # citation strings for the releases in use
    python scdb.py jcs kennedy                # Judicial Common Space scores (justices and CoA judges)
    python scdb.py state UT                   # a state's selection history and election counts
    python scdb.py state durham               # every election a state justice stood in

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


def data_path(rel, what=None):
    """Locate a data file, allowing large tables to live outside the skill.

    Looked for first under the skill's own `data/`, then under the directory in
    $SCDB_DATA_EXTRA, keeping the same relative path. That lets a slim upload --
    one without `coa/coa_cases.csv.gz`, which is 37 of the bundle's 43 MB -- work
    on a machine that keeps the big file locally:

        export SCDB_DATA_EXTRA=~/judicial-data/scdb-expert/data

    Raises with both paths named rather than failing obscurely."""
    p = os.path.join(DATA, rel)
    if os.path.exists(p):
        return p
    extra = os.environ.get("SCDB_DATA_EXTRA")
    if extra:
        q = os.path.join(os.path.expanduser(extra), rel)
        if os.path.exists(q):
            return q
    msg = [f"{what or rel} is not available.", f"  not in the skill: {p}"]
    if extra:
        msg.append(f"  not under SCDB_DATA_EXTRA: {q}")
    else:
        msg.append("  $SCDB_DATA_EXTRA is unset; point it at a data/ directory"
                   " that has this file,")
        msg.append("  e.g. export SCDB_DATA_EXTRA=~/judicial-data/scdb-expert/data")
    raise FileNotFoundError("\n".join(msg))
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
    if os.path.isdir(os.path.join(DATA, "jcs")):
        out += JCS_CITATIONS
    if os.path.isdir(os.path.join(DATA, "coa")):
        out += COA_CITATIONS
    if os.path.isdir(os.path.join(DATA, "state")):
        out += STATE_CITATIONS
    return out


# ---------------------------------------------------------------- Judicial Common Space
JCS = os.path.join(DATA, "jcs")
_JCS_FILES = {"justice": "jcs_justice_term.csv", "coa": "jcs_coa_judges.csv",
              "medians": "jcs_medians.csv", "circuits": "circuits.csv"}
JCS_CITATIONS = [
    "Lee Epstein, Andrew D. Martin, Jeffrey A. Segal, and Chad Westerland. 2007. "
    "\"The Judicial Common Space.\" Journal of Law, Economics, & Organization 23(2): 303-325.",
]


def jcs(which="justice"):
    """Judicial Common Space tables.
    'justice'         term, justice (SCDB id), justiceName, jcs      (OT1937-OT2022)
    'coa'             courts of appeals judges: judge_key, name, circuit, scdb_caseSource, jcs
    'medians'         by calendar year: president, house/senate/sc medians, circuit medians & SDs
    'circuit_medians' medians reshaped long: year, term, circuit, circuit_name, scdb_caseSource, median, sd
    'circuits'        JCS circuit number -> name -> SCDB caseSource code"""
    if which == "circuit_medians":
        m, circ = jcs("medians"), jcs("circuits")
        rows = []
        for c in circ.circuit:
            rows.append(m[["year", "term"]].assign(circuit=c, median=m[f"circuit_median{c}"],
                                                   sd=m[f"circuit_sd{c}"]))
        out = pd.concat(rows, ignore_index=True).merge(circ[["circuit", "circuit_name", "scdb_caseSource"]],
                                                       on="circuit")
        # 1924 appears twice in the medians table (different president values, identical circuit
        # values), so drop exact duplicates
        out = out.dropna(subset=["median"]).drop_duplicates(["year", "circuit", "median", "sd"])
        return out.reset_index(drop=True)
    if which not in _JCS_FILES:
        raise ValueError(f"which must be one of {sorted(_JCS_FILES) + ['circuit_medians']}")
    df = pd.read_csv(os.path.join(JCS, _JCS_FILES[which]))
    if "term" in df.columns:
        df["term"] = df["term"].astype("Int64")
    return df


def add_jcs(v, col="jcs"):
    """Attach each justice's JCS score for that term to justice-level SCDB rows (merge on justice, term).
    Coverage is OT1937-OT2022; other rows get <NA>."""
    j = jcs("justice")[["term", "justice", "jcs"]].rename(columns={"jcs": col})
    j["justice"] = j["justice"].astype("Int64")
    out = v.merge(j, on=["term", "justice"], how="left", validate="many_to_one")
    return out


def add_medians(df, cols=("sc_median", "president", "house_median", "senate_median")):
    """Attach political-environment medians by SCDB term. The medians row for term t is
    calendar year t+1 (the year most of the term's decisions come down)."""
    m = jcs("medians").dropna(subset=["term"])[["term", *cols]]
    return df.merge(m, on="term", how="left", validate="many_to_one")


def add_circuit_medians(c, year_offset=0):
    """For cases reviewing a federal court of appeals (caseSource in the 13 circuit codes), attach
    the JCS median and SD of that circuit. Uses calendar year = term + 1 + year_offset; the
    reviewed decision usually came 1-2 years earlier, so try year_offset=-1 or -2 as robustness."""
    cm = jcs("circuit_medians")[["year", "scdb_caseSource", "median", "sd"]].rename(
        columns={"median": "circuit_median", "sd": "circuit_sd", "scdb_caseSource": "caseSource"})
    cm["caseSource"] = cm["caseSource"].astype("Int64")
    out = c.assign(_year=(c["term"] + 1 + year_offset).astype("Int64"))
    out = out.merge(cm.rename(columns={"year": "_year"}), on=["_year", "caseSource"], how="left",
                    validate="many_to_one")
    return out.drop(columns="_year")


# ------------------------------------------- Courts of Appeals (CCAD)
COA = os.path.join(DATA, "coa")
_COA_FILES = {"cases": "coa_cases.csv.gz", "crosswalk": "crosswalk.csv.gz"}
COA_CITATIONS = [
    "Eitan Sapiro-Gheiler and Jonathan P. Kastellec. Comprehensive Court of Appeals "
    "Database, Release 09-2026. Princeton University.",
]

# The CCAD's disposition columns are described as using \"the SCDB scheme\", but the
# numbering differs: codes 1-8 sit one below SCDB's, and 9/0 wrap around. Verified
# against the code lists in both codebooks and against 6,582 tier-A linked pairs.
# CCAD 11 (\"affirmed, vacated, and remanded\") has no SCDB equivalent; the CCAD
# codebook says to treat it as its code 6, which is SCDB 7.
COA_DISPOSITION_TO_SCDB = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 1,
                           10: 10, 0: 11, 11: 7}
# The CCAD codebook states that EVERY direction variable uses the Songer convention.
# That holds only for the reproduced songer_gt_* fields. The LLM-coded direction
# columns (scdb_first_direction_oneshot, scdb_second_direction_mech, ...) are already
# in SCDB coding -- 1 conservative, 2 liberal, 3 unspecifiable -- and need no remap.
# Established two ways: criminal appeals brought by the accused code 1 when the
# conviction is affirmed (98.9%) and 2 when it is reversed (82-96%); and code 3 covers
# 100% of Private Action and Interstate Relations, the two issue areas SCDB hardcodes
# as unspecifiable. See references/coa.md.
SONGER_DIRECTION_TO_SCDB = {1: 1, 3: 2, 0: 3, 2: 3}   # cons/lib/not-ascertained/mixed


_COA_TEXT = {"caseid", "citation", "docket_number", "scdb_first_appellant_name",
             "scdb_first_respondent_name", "caseId", "caseName", "usCite",
             "coa_caseid", "coa_citation", "confidence",
             "author_name", "author_appointing_president", "dis1_name", "conc1_name",
             "j1_name", "j1_appointing_president", "j2_name", "j3_name",
             "enbanc_id", "enbanc_name"}
_COA_DATES = {"decision_date", "coa_date", "scotus_date"}
# Ideology (Giles-Hettinger-Peppers), ages and the panel aggregates are continuous.
_COA_FLOAT = {"score", "name_score", "margin", "gap_z",
              "author_ghp", "author_age", "author_tenure", "dis1_ghp", "conc1_ghp",
              "j1_ghp", "j2_ghp", "j3_ghp",
              "ghp_min", "ghp_max", "ghp_med", "ghp_mean", "age_med", "tenure_med"}


def coa(which="cases", parse=True):
    """Comprehensive Court of Appeals Database tables.
    'cases'     512,263 published CoA opinions 1880-2025 x 28 vars (one row per case)
    'crosswalk' 8,265 CoA cases linked to an SCDB case, with a confidence tier

    Circuit numbering here is the CCAD's: 0 = D.C., 1-11 by number, 12 = Federal.
    `jcs(\"circuits\")` crosswalks it to the JCS and SCDB schemes. Coded variables
    come back as Int64 and dates as datetime, matching `load()`."""
    if which not in _COA_FILES:
        raise ValueError(f"which must be one of {sorted(_COA_FILES)}")
    df = pd.read_csv(data_path(os.path.join("coa", _COA_FILES[which]),
                               f'coa("{which}")'), dtype=str,
                     keep_default_na=False, low_memory=False)
    if not parse:
        return df
    for c in df.columns:
        if c in _COA_TEXT:
            df[c] = df[c].replace("", None)
        elif c in _COA_DATES:
            df[c] = pd.to_datetime(df[c].replace("", None), errors="coerce")
        elif c in _COA_FLOAT:
            df[c] = pd.to_numeric(df[c].replace("", None))
        elif c == "mutual":
            df[c] = df[c].map({"True": True, "False": False}).astype("boolean")
        else:
            df[c] = pd.to_numeric(df[c].replace("", None)).astype("Int64")
    return df


def add_coa(c, confidence=("A",), prefix="coa_"):
    """Attach the reviewed courts-of-appeals case to SCDB case-level rows.

    Links come from `coa(\"crosswalk\")`, which matches on circuit + decision-date
    window + party-name similarity -- neither database carries the other's
    citation. `confidence` selects which tiers to accept:
        'A'  mutual best match, score >= 0.50   (~1.2% false-positive rate)
        'B'  mutual best match, score >= 0.35   (~1.8% cumulative)
        'C'  score >= 0.20                      (use only with inspection)
    Unlinked SCDB cases get <NA>. See references/coa.md before using tier C."""
    x = coa("crosswalk")
    x = x[x.confidence.isin(confidence)]
    cols = {"coa_caseid": f"{prefix}caseid", "coa_citation": f"{prefix}citation",
            "coa_date": f"{prefix}date", "gap_days": f"{prefix}gap_days",
            "score": f"{prefix}match_score", "confidence": f"{prefix}match_confidence"}
    x = x[["caseId"] + list(cols)].rename(columns=cols)
    return c.merge(x, on="caseId", how="left", validate="one_to_one")


def add_scdb(d, confidence=("A",)):
    """The reverse of add_coa: attach the reviewing SCDB case to CCAD rows.
    Adds caseId, caseName, usCite, term, scotus_date and the match diagnostics;
    CoA cases the Supreme Court never reviewed (the vast majority) get <NA>."""
    x = coa("crosswalk")
    x = x[x.confidence.isin(confidence)]
    x = x[["coa_caseid", "caseId", "caseName", "usCite", "term", "scotus_date",
           "gap_days", "score", "confidence"]].rename(
        columns={"coa_caseid": "caseid", "score": "match_score",
                 "confidence": "match_confidence"})
    return d.merge(x, on="caseid", how="left", validate="one_to_one")


def add_coa_circuit_medians(d, year_col="year"):
    """Attach the deciding circuit's JCS median and SD for the year of the decision.

    Lets a panel be compared with its circuit: `ghp_med - circuit_median` is how far
    the panel sat from the circuit as a whole. The panel scores (`author_ghp`,
    `ghp_*`) are Giles-Hettinger-Peppers scores, the same measure behind the JCS
    appeals-judge scores, so the two are on one scale (about -1 liberal to
    +1 conservative). Circuit medians run 1924-2024; cases outside that get <NA>."""
    cm = jcs("circuit_medians")[["year", "coa_circuit", "median", "sd"]].rename(
        columns={"median": "circuit_median", "sd": "circuit_sd"}) \
        if "coa_circuit" in jcs("circuit_medians").columns else None
    if cm is None:                      # older circuits.csv without CCAD numbering
        xw = jcs("circuits")[["scdb_caseSource", "coa_circuit"]]
        cm = jcs("circuit_medians")[["year", "scdb_caseSource", "median", "sd"]].merge(
            xw, on="scdb_caseSource", how="left").rename(
            columns={"median": "circuit_median", "sd": "circuit_sd"})
        cm = cm[["year", "coa_circuit", "circuit_median", "circuit_sd"]]
    cm["coa_circuit"] = cm["coa_circuit"].astype("Int64")
    out = d.assign(_y=d[year_col].astype("Int64"), _c=d["circuit"].astype("Int64"))
    out = out.merge(cm.rename(columns={"year": "_y", "coa_circuit": "_c"}),
                    on=["_y", "_c"], how="left", validate="many_to_one")
    return out.drop(columns=["_y", "_c"])


def coa_labels(variable):
    """Code -> label for a CCAD variable, mirroring labels() on the SCDB side.
    `scdb_first_broad_area` and `scdb_second_sub_area` reuse the SCDB issueArea /
    issue code lists exactly; the party-category, disposition and direction scales
    do NOT -- see references/coa.md."""
    out = {}
    with open(os.path.join(REF, "coa_value_labels.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["variable"] == variable:
                out[int(r["code"])] = r["label"]
    if not out:
        raise KeyError(f"no CCAD labels for {variable!r}; try: "
                       f"{sorted(coa_labelled_vars())}")
    return out


def coa_labelled_vars():
    """CCAD variables that have a code table."""
    with open(os.path.join(REF, "coa_value_labels.csv"), encoding="utf-8") as f:
        return sorted({r["variable"] for r in csv.DictReader(f)})


def label_coa(df, variables=None):
    """Add a <var>_label column for each coded CCAD variable present (all of them
    by default), mirroring label() on the SCDB side."""
    have = set(coa_labelled_vars())
    variables = [v for v in (variables or sorted(have)) if v in df.columns and v in have]
    out = df.copy()
    for v in variables:
        out[f"{v}_label"] = out[v].map(coa_labels(v))
    return out


def coa_disposition_to_scdb(s):
    """Remap a CCAD disposition column to SCDB caseDisposition/lcDisposition codes."""
    return pd.Series(s).map(COA_DISPOSITION_TO_SCDB).astype("Int64")


def songer_direction_to_scdb(s):
    """Remap a Songer-convention direction (0 n/a, 1 cons, 2 mixed, 3 lib) to SCDB's
    (1 conservative, 2 liberal, 3 unspecifiable). Mixed collapses into 3.

    Apply this to the reproduced `songer_gt_*` direction fields ONLY. The CCAD's own
    LLM-coded direction columns are already in SCDB coding -- see references/coa.md."""
    return pd.Series(s).map(SONGER_DIRECTION_TO_SCDB).astype("Int64")


# ------------------------------------------- Courts of Appeals seats
_SEAT_FILES = {"seats": "coa_seats.csv.gz", "spells": "coa_seat_spells.csv.gz"}
_SEAT_TEXT = {"seat_id", "circuit_name", "judge_name", "predecessor", "state",
              "president", "pres_party", "left_because", "creating_statute",
              "jcs_match", "created_by"}
_SEAT_FLOAT = {"jcs", "pred_jcs", "jcs_shift", "vacancy_years"}
_SEAT_BOOL = {"sitting", "filled_now"}
SEAT_LAST_YEAR = 2026


def seats(which="seats", parse=True):
    """Courts-of-appeals judgeships and who has held them.

    'seats'   203 judgeships: the statute that created each, its span, how many
              judges have held it, whether it is filled now
    'spells'  868 occupancies: judge, dates, predecessor, ideology and the shift
              from the previous occupant, how the seat came open

    A *seat* is an authorized judgeship. Succession comes from the FJC's
    official Seat IDs, so it is looked up rather than inferred. Occupancy ends
    at senior status, which vacates the judgeship. Circuit numbering is the JCS
    scheme (12 = D.C., 13 = Federal), as in `jcs("circuits")` -- not the CCAD's.
    See references/coa_seats.md."""
    if which not in _SEAT_FILES:
        raise ValueError(f"which must be one of {sorted(_SEAT_FILES)}")
    try:
        path = data_path(os.path.join("coa", _SEAT_FILES[which]), f'seats("{which}")')
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"{e}\n  or rebuild: python scripts/build_seats.py "
            "--fjc fjc-raw/federal-judicial-service.csv.gz --out data/coa\n"
            "  see references/coa_seats.md") from None
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if not parse:
        return df
    for c in df.columns:
        if c in _SEAT_TEXT:
            df[c] = df[c].replace("", None)
        elif c in _SEAT_FLOAT:
            df[c] = pd.to_numeric(df[c].replace("", None))
        elif c in _SEAT_BOOL:
            df[c] = df[c].map({"True": True, "False": False}).astype("boolean")
        else:
            df[c] = pd.to_numeric(df[c].replace("", None)).astype("Int64")
    return df


def seat_panel(start=None, end=None):
    """Derive the circuit x seat x year panel from the occupancy spells.

    One row per seat-year, so a vacant seat-year is simply absent and a gap in
    a seat's rows is a real vacancy. Derived rather than stored, so it cannot
    drift away from `seats("spells")`."""
    sp = seats("spells")
    lo = int(start) if start is not None else int(sp.occ_start.min())
    hi = int(end) if end is not None else SEAT_LAST_YEAR
    sp = sp[(sp.occ_end >= lo) & (sp.occ_start <= hi)].copy()
    sp["a"] = sp.occ_start.clip(lower=lo)
    sp["b"] = sp.occ_end.clip(upper=hi)
    out = sp.loc[sp.index.repeat((sp.b - sp.a + 1).astype(int))].copy()
    out["year"] = out.a + out.groupby(level=0).cumcount()
    cols = ["circuit", "circuit_name", "seat_no", "seat_id", "year", "judge_name",
            "state", "jcs", "pres_party", "president", "occupancy", "creating_statute"]
    return (out[[c for c in cols if c in out.columns]]
            .sort_values(["circuit", "seat_no", "year"], kind="stable")
            .reset_index(drop=True))


def find_judge(query, circuit=None):
    """Occupancies whose judge matches `query`, case- and accent-insensitively.

    Every word of the query must appear in the name, in any order, so
    "coney barrett" finds "Barrett, Amy Coney" and "gelpi" finds "Gelpí".
    The courts-of-appeals analogue of `justice()`."""
    import matchjcs
    sp = seats("spells")
    words = [w for w in re.split(r"[^\w]+", matchjcs._fold(query)) if w]
    if not words:
        return sp.iloc[0:0]

    def hits(name):
        n = matchjcs._fold(name)
        return all(w in n for w in words)

    hit = sp[sp.judge_name.fillna("").map(hits)]
    if circuit is not None:
        hit = hit[hit.circuit == circuit]
    return hit.sort_values(["judge_name", "occ_start"]).reset_index(drop=True)


def seat_history(circuit, seat_no):
    """Every judge who has held one judgeship, in order."""
    sp = seats("spells")
    return (sp[(sp.circuit == circuit) & (sp.seat_no == seat_no)]
            .sort_values("occupancy").reset_index(drop=True))


def court_composition(circuit, year):
    """Who sat on one circuit in one year, one row per filled seat."""
    p = seat_panel(year, year)
    return p[p.circuit == circuit].sort_values("seat_no").reset_index(drop=True)


# ------------------------------------------- State supreme court elections (Kritzer)
STATE = os.path.join(DATA, "state")
_STATE_FILES = {"elections": "elections.csv.gz", "seats": "seats.csv.gz",
                "retention": "retention.csv.gz", "selection": "selection.csv",
                "states": "states.csv", "fixes": "fixes.csv"}
_STATE_TEXT = {"state", "state2", "state_name", "district", "District", "CourtType",
               "Candidates", "incumbent", "uncontested", "Primary", "circuit", "name",
               "PartyApptGov", "notes", "Notes", "MiscVotes", "DateAppointed", "court",
               "method", "table", "column", "old", "new", "reason"}
_STATE_FLOAT = {"pct_yes", "correlation", "VoteRatio", "VotePrimary", "VoteRunOff",
                "VoteGeneral", "PctPrimary", "PctRunoff", "PctGeneral"}
STATE_CITATIONS = [
    "Herbert M. Kritzer. State Supreme Court Election Archive (updated February 9, 2024). "
    "University of Minnesota Law School. Harvard Dataverse [add DOI].",
    "Herbert M. Kritzer. 2015. Justices on the Ballot: Continuity and Change in State "
    "Supreme Court Elections. New York: Cambridge University Press.",
]
STATE_SELECTION_END = 2023          # last election year in the archive


def state_elections(which="elections", parse=True):
    """State supreme court election tables (Kritzer's archive, 1936-2023).

    'elections'  2,672 contested primaries, run-offs and generals (plus unopposed
                 generals), 1946-2023; candidates in wide form CandName1..24 --
                 see state_candidates() for one row per candidate
    'seats'      2,302 seats up for election with competitiveness measures
                 (Pct* are percentages, 0-100)
    'retention'  896 retention-type elections, 1936-2022
    'selection'  derived: selection-method spans by state and court
    'states'     Kritzer stateid <-> postal code <-> SCDB caseSourceState
    'fixes'      the corrections this build applied to the archive

    Columns keep the archive's names. Keys: `seatid` (state number x 1000 + seat
    sequence) and `electid` (seatid x 100 + electtype). The three tables name the
    state differently: `state` (postal) in elections/seats, `state2` (postal) in
    retention, where `state` is a 1-20 sequence. `stateid` (1 Alabama .. 50
    Wyoming) is common to all three. See references/state_elections.md."""
    if which not in _STATE_FILES:
        raise ValueError(f"which must be one of {sorted(_STATE_FILES)}")
    path = data_path(os.path.join("state", _STATE_FILES[which]), f'state_elections("{which}")')
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if not parse:
        return df
    for c in df.columns:
        if c in _STATE_TEXT or (which == "elections" and c.startswith("CandName")):
            df[c] = df[c].replace("", None)
        elif c == "in_archive":
            df[c] = df[c].map({"True": True, "False": False}).astype("boolean")
        else:
            x = pd.to_numeric(df[c].replace("", None), errors="coerce")
            if c not in _STATE_FLOAT and (x.dropna() % 1 == 0).all():
                x = x.astype("Int64")
            df[c] = x
    return df


def state_candidates(elections=None):
    """One row per candidate per election, derived from the wide Election table.

    Columns: electid, seatid1, stateid, state, year, CourtType, CJ, district,
    numseats, electtype, cand (0 = unopposed, else 1-24), name, votes, share
    (votes / TotalVoteCount), rank (by votes within the election), CandType,
    IncumType, YrAppointed, Party. Unopposed candidates have no vote count.
    Winners are not coded in the archive: in a general election the top
    `numseats` vote-getters win, but primaries advance a varying number."""
    e = state_elections("elections") if elections is None else elections
    keep = ["electid", "seatid1", "stateid", "state", "year", "CourtType", "CJ", "district",
            "numseats", "electtype", "TotalVoteCount"]
    parts = []
    for k in range(25):
        name = e[f"CandName{k}"]
        sub = e.loc[name.notna(), keep].copy()
        sub["cand"] = k
        sub["name"] = name[name.notna()].str.strip()
        sub["votes"] = e.loc[name.notna(), f"votes{k}"] if k else pd.NA
        for v in ("CandType", "IncumType", "YrAppointed", "Party"):
            col = f"{v}{k}"
            sub[v] = e.loc[name.notna(), col] if col in e else pd.NA
        parts.append(sub)
    out = pd.concat(parts, ignore_index=True)
    out["votes"] = pd.to_numeric(out["votes"]).astype("Int64")
    out["share"] = (out.votes / out.TotalVoteCount).astype("Float64")
    out["rank"] = out.groupby("electid").votes.rank(ascending=False, method="min").astype("Int64")
    return (out.drop(columns="TotalVoteCount")
            .sort_values(["stateid", "year", "electid", "cand"]).reset_index(drop=True))


def state_labels(variable, table=None):
    """Code -> label for a state-election variable. CandType, IncumType and Party
    cover their numbered series (CandType0..24 etc.)."""
    import re as _re
    base = _re.sub(r"\d+$", "", variable)
    out = {}
    with open(os.path.join(REF, "state_value_labels.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["variable"] == base and (table is None or r["table"] == table):
                k = r["code"]
                out[int(k) if k.lstrip("-").isdigit() else k] = r["label"]
    if not out:
        raise KeyError(f"no state-election labels for {variable!r}")
    return out


def label_state(df, variables=None, table=None):
    """Add <var>_label columns for the coded state-election variables present.
    Pass table= ("elections", "seats", "retention") where a name is shared --
    `electtype` and `CourtType` are coded differently across the tables."""
    with open(os.path.join(REF, "state_value_labels.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    have = {r["variable"] for r in rows if table is None or r["table"] == table}
    import re as _re
    cols = variables or [c for c in df.columns if _re.sub(r"\d+$", "", c) in have]
    out = df.copy()
    for v in cols:
        out[f"{v}_label"] = out[v].map(state_labels(v, table))
    return out


def state_selection(state=None, year=None, court="sc"):
    """How a state chose its high court in a year, from the derived spans.

    With no year, returns that state's spans (or all states' with no state).
    With a year, returns the list of methods in use -- usually one; two where
    winners of partisan elections later stand for retention (IL, PA, NM) --
    [] for a state with no elections that year (one outside the archive, or
    New York after 1974), and None where the archive cannot say (before 1946
    or a state's first observed election). Spans ending in the archive's last
    year are treated as still in force. court: "sc", or "cr" for the Texas and
    Oklahoma Courts of Criminal Appeals."""
    sel = state_elections("selection")
    if state is None:
        return sel
    st = state.upper()
    g = sel[(sel.state == st) & (sel.court == court)]
    if year is None:
        return g.reset_index(drop=True)
    y = int(year)
    if g.empty:
        known = state_elections("states").set_index("state").in_archive
        if st not in known.index:
            raise KeyError(f"unknown state {state!r}")
        return [] if 1946 <= y else None
    end = g.end.where(g.end < STATE_SELECTION_END, 10**4)
    hit = g[(g.start <= y) & (end >= y)]
    if not hit.empty:
        return sorted(hit.method)
    return [] if y > g.end.max() else None


def add_state_selection(c, sources=(300,), year_col="term"):
    """Attach the reviewed state court's selection method to SCDB case rows.

    For cases whose `caseSource` is a state court (300 = state supreme court by
    default; add 301/302 for intermediate and trial courts), adds
      source_state      postal code, from caseSourceState
      state_selection   e.g. "partisan", "nonpartisan", "retention",
                        "partisan+retention", "none" (justices not elected),
                        <NA> where the archive cannot say (mostly pre-1946)
    keyed on `term` by default. SCDB's 300 does not separate Texas's and
    Oklahoma's two high courts; their methods agree in every year, so this uses
    the supreme court's. Other rows get <NA>."""
    st = state_elections("states")
    code_to_state = dict(zip(st.scdb_state, st.state))
    sel = state_elections("selection")
    sel = sel[sel.court == "sc"]
    in_arch = set(st[st.in_archive].state)
    rows = []
    for s_, g in sel.groupby("state"):
        lo, hi = int(g.start.min()), int(g.end.max())
        open_end = hi >= STATE_SELECTION_END
        for y in range(lo, max(hi, 2030 if open_end else hi) + 1):
            end = g.end.where(g.end < STATE_SELECTION_END, 10**4)
            m = sorted(g[(g.start <= y) & (end >= y)].method)
            rows.append((s_, y, "+".join(m) if m else "none"))
        if not open_end:
            rows += [(s_, y, "none") for y in range(hi + 1, 2031)]
    for s_ in set(st.state) - in_arch:
        rows += [(s_, y, "none") for y in range(1946, 2031)]
    lut = pd.DataFrame(rows, columns=["source_state", "_y", "state_selection"])
    out = c.copy()
    is_state = out["caseSource"].isin(list(sources))
    out["source_state"] = out["caseSourceState"].map(code_to_state).where(is_state)
    out["_y"] = out[year_col].astype("Int64")
    out = out.merge(lut, on=["source_state", "_y"], how="left", validate="many_to_one")
    out["state_selection"] = out["state_selection"].astype("string")
    return out.drop(columns="_y")


def find_state_judge(query, state=None):
    """Every election a judge stood in -- contested, unopposed, or retention --
    matched case- and accent-insensitively on all words of the query, in any
    order. Names are spelled as in the archive, which varies ("Jim Rice",
    "James A. Rice"), so search on a surname and check the hits."""
    import unicodedata

    def fold(s):
        s = unicodedata.normalize("NFKD", str(s))
        return "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    words = [w for w in re.split(r"[^\w]+", fold(query)) if w]
    hit = lambda n: n is not None and all(w in fold(n) for w in words)
    cand = state_candidates()
    cand = cand[cand.name.map(hit)].assign(kind="election")
    r = state_elections("retention")
    r = r[r.name.map(hit)].rename(columns={"state2": "state_"})
    r = r.drop(columns="state").rename(columns={"state_": "state"}).assign(kind="retention")
    cols = ["kind", "state", "year", "electid", "electtype", "name", "votes", "share",
            "rank", "CandType", "yes", "no", "pct_yes", "circuit", "district"]
    out = pd.concat([cand, r], ignore_index=True)
    if state:
        out = out[out.state == state.upper()]
    return (out[[c for c in cols if c in out.columns]]
            .sort_values(["state", "year", "electid"]).reset_index(drop=True))


# ---------------------------------------------------------------- CLI
CASE_FIELDS =["caseName", "usCite", "sctCite", "ledCite", "lexisCite", "docket", "term",
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


def _cli_state(arg):
    """`state UT` -> selection history and election counts; `state durham` -> a judge."""
    st = state_elections("states")
    if arg.upper() in set(st.state):
        ab = arg.upper()
        row = st[st.state == ab].iloc[0]
        print(f"{row.state_name} (stateid {row.stateid}, SCDB caseSourceState {row.scdb_state})")
        sel = state_elections("selection")
        sel = sel[sel.state == ab]
        if sel.empty:
            print("  no supreme court elections 1946-2023 (justices not elected)")
            return
        for _, r in sel.iterrows():
            court = "" if r.court == "sc" else " [Court of Criminal Appeals]"
            end = "present" if r.end >= STATE_SELECTION_END else r.end
            print(f"  {r.start}-{end:<8} {r.method:<12} {r.n_obs:>4} elections observed "
                  f"{r.first_obs}-{r.last_obs}{court}")
        e = state_elections("elections")
        e = e[e.state == ab]
        r = state_elections("retention")
        r = r[r.state2 == ab]
        lab = state_labels("electtype", "elections")
        if len(e):
            print(f"  election records: {len(e)} ({e.year.min()}-{e.year.max()})")
            for k, n in e.electtype.value_counts().sort_index().items():
                print(f"    {n:>4}  {lab[int(k)]}")
        if len(r):
            print(f"  retention records: {len(r)} ({r.year.min()}-{r.year.max()}), "
                  f"{int((r.pct_yes < 0.5).sum())} under 50% yes")
        return
    hit = find_state_judge(arg)
    if hit.empty:
        print("no state supreme court candidate matches"); return
    lab = state_labels("electtype", "elections")
    for _, r in hit.iterrows():
        what = lab.get(int(r.electtype), str(r.electtype))
        if r.kind == "retention":
            res = f"yes {r.yes:,} / no {r.no:,} ({r.pct_yes:.1%} yes)"
        elif pd.isna(r.votes):
            res = "unopposed"
        else:
            sh = "" if pd.isna(r.share) else f", {r.share:.1%}"
            res = f"{r.votes:,} votes{sh}, placed {r['rank']}"
        print(f"{r.state} {r.year}  {r['name']:<28} {what:<40} {res}")


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
        jm = os.path.join(JCS, "MANIFEST.json")
        if os.path.exists(jm):
            j = json.load(open(jm, encoding="utf-8"))
            print(f"  JCS      justices {j['justice_term']['terms'][0]}-{j['justice_term']['terms'][1]} "
                  f"({j['justice_term']['rows']} justice-terms), {j['coa_judges']['judges']} appeals judges, "
                  f"medians {j['medians']['years'][0]}-{j['medians']['years'][1]}")
        sm = os.path.join(STATE, "MANIFEST.json")
        if os.path.exists(sm):
            j = json.load(open(sm, encoding="utf-8"))
            print(f"  state    elections {j['elections.csv.gz']['rows']:,} "
                  f"({j['elections.csv.gz']['years'][0]}-{j['elections.csv.gz']['years'][1]}), "
                  f"seats {j['seats.csv.gz']['rows']:,}, retention {j['retention.csv.gz']['rows']:,} "
                  f"({j['retention.csv.gz']['years'][0]}-{j['retention.csv.gz']['years'][1]}); "
                  f"{j['fixes']} corrections to the archive")
    elif cmd == "find":
        _print_hits(find(load("case"), arg))
    elif cmd == "case":
        _cli_case(arg)
    elif cmd == "jcs":
        q = arg.lower()
        j = jcs("justice")
        hit = j[j.justiceName.str.lower().str.contains(q, regex=False)]
        for name, g in hit.groupby("justiceName"):
            print(f"{name} (SCDB id {int(g.justice.iloc[0])}): JCS terms {g.term.min()}-{g.term.max()}, "
                  f"mean {g.jcs.mean():+.3f}, range {g.jcs.min():+.3f} to {g.jcs.max():+.3f}")
            print("   " + "  ".join(f"{t}:{x:+.3f}" for t, x in zip(g.term, g.jcs)))
        c = jcs("coa")
        hc = c[c["name"].map(_norm).str.contains(_norm(arg), regex=False)]
        if len(hc):
            print(hc[["name", "circuit_name", "jcs"]].to_string(index=False))
        if hit.empty and hc.empty:
            print("no justice or courts of appeals judge matches")
    elif cmd == "coa":
        d = coa("cases")
        q = _norm(arg)
        hit = d[(d.scdb_first_appellant_name.fillna("").map(_norm).str.contains(q, regex=False) |
                 d.scdb_first_respondent_name.fillna("").map(_norm).str.contains(q, regex=False) |
                 d.citation.fillna("").str.replace(" ", "", regex=False).str.contains(
                     arg.replace(" ", ""), case=False, regex=False))]
        if hit.empty:
            print("no courts of appeals case matches"); return
        circ = jcs("circuits").set_index("coa_circuit").circuit_name.to_dict()
        link = coa("crosswalk").set_index("coa_caseid")
        for _, r in hit.head(25).iterrows():
            name = f"{r.scdb_first_appellant_name} v. {r.scdb_first_respondent_name}"
            print(f"{r.citation or '(no cite)':>14}  {circ.get(r.circuit, '?'):<17} "
                  f"{str(r.decision_date.date()) if pd.notna(r.decision_date) else '':<11} {name[:70]}")
            if r.caseid in link.index:
                l = link.loc[r.caseid]
                l = l.iloc[0] if isinstance(l, pd.DataFrame) else l
                print(f"{'':>14}  -> SCOTUS: {l.caseName[:60]} {l.usCite or ''} "
                      f"(tier {l.confidence}, score {l.score:.2f})")
        if len(hit) > 25:
            print(f"... and {len(hit) - 25} more")
    elif cmd == "seat":
        try:
            hit = find_judge(arg)
        except FileNotFoundError as e:
            print(e); return
        if hit.empty:
            print("no courts of appeals judge matches"); return
        for _, r in hit.iterrows():
            end = "present" if pd.isna(r.end) else int(r.end)
            j = "   .  " if pd.isna(r.jcs) else f"{r.jcs:+.3f}"
            print(f"{r.judge_name}  [{r.circuit_name}, seat {r.seat_no}, "
                  f"occupant {r.occupancy}]")
            print(f"    {int(r.occ_start)}-{end}   JCS {j}"
                  f"   left by {r.left_because or 'still sitting'}")
            if pd.notna(r.predecessor):
                sh = "" if pd.isna(r.jcs_shift) else f", shift {r.jcs_shift:+.3f}"
                print(f"    replaced {r.predecessor}{sh}")
            hist = seat_history(int(r.circuit), int(r.seat_no))
            chain = " -> ".join(n.split(",")[0] for n in hist.judge_name)
            print(f"    seat created by {hist.iloc[0].creating_statute or '(pre-1891)'}: "
                  f"{chain}")
            print()
    elif cmd == "state":
        _cli_state(arg)
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
