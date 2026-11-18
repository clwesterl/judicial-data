"""Build the state supreme court election tables from Kritzer's archive.

Source: Herbert M. Kritzer, State Supreme Court Election Archive (updated
February 9, 2024), distributed as .7z-compressed Excel files. The archive's
three core datasets become three tables here, plus a derived selection-method
table and a state crosswalk to the SCDB:

    elections.csv.gz   one row per contested primary / run-off / general election,
                       1946-2023, up to 24 candidates in wide form (ElectionDataset)
    seats.csv.gz       one row per seat up for election, with competitiveness
                       measures (SeatsDataset)
    retention.csv.gz   one row per retention-type election, 1936-2022 (RetentionDataset)
    selection.csv      derived: how each state chose its high court(s), as spans
                       of years, from the elections actually observed
    states.csv         Kritzer stateid <-> postal code <-> SCDB caseSourceState
    fixes.csv          every correction applied below: old value, new value, why
    MANIFEST.json      sources, row counts, SHA-256 digests

Columns keep the archive's names and order. Two conversions apply throughout:
the archive's -9 missing-value code becomes blank, and dates are written as
ISO yyyy-mm-dd. Every other change is a row in FIXES below; each fix asserts
the value it expects to replace, so a corrected future release fails loudly
instead of being silently double-corrected.

Which file each table comes from matters. The standalone ElectionDataset.7z
(workbook saved 2024-03-07) is a corrected version of the copy inside
AllFiles.7z (2024-02-09): the AllFiles copy has 39 duplicated electids that the
standalone one resolves. SeatsDataset exists only in AllFiles; RetentionDataset
is byte-identical in both.

Usage:
    python build_state_elections.py --raw state-elections-raw --out data/state
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import sys
import warnings

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import un7z

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

DATA_END = 2023          # last election year in the archive
SPAN_GAP = 12            # years without an election of a kind before a span breaks

# ------------------------------------------------------------------ corrections
# (table, {column: value, ...} identifying exactly one row, column, old, new, reason)
# A column of "__drop__" deletes the row.
AZ22 = "Ballotpedia, Arizona Supreme Court elections (statewide canvass totals; " \
       "its 2020 Arizona figures match the archive exactly)"
FIXES = [
    # --- Utah 1970-1984: uncontested nonpartisan elections that reverted to a
    # retention vote. The codebook says these carry electtype 11 and share one
    # electid across the Election and Retention datasets. The Election file codes
    # them 14 (undocumented) and the Retention file codes the 1978-84 ones 20.
    *[("elections", {"electid": old}, "electtype", 14, 11,
       "undocumented code 14; codebook code for an uncontested nonpartisan election "
       "that reverted to retention is 11") for old in
      (4401614, 4401714, 4402014, 4402114, 4402214, 4402314)],
    *[("elections", {"electid": old}, "electid", old, old - 3,
       "electid = seatid + electtype; follows the electtype correction and makes "
       "the Election and Retention records share one electid as the codebook says")
      for old in (4401614, 4401714, 4402014, 4402114, 4402214, 4402314)],
    ("elections", {"electid": 4402011}, "year", 1980, 1982,
     "Durham was appointed in 1982; SeatsDataset and RetentionDataset both put "
     "seat 44020 in 1982"),
    *[("elections", {"electid": old}, "electtype", 1, 11,
       "1978 Utah uncontested incumbent; SeatsDataset codes it R (reverted to "
       "retention) and the Notes field says so") for old in (4450101, 4450201)],
    *[("elections", {"electid": old}, "electid", old, old + 10,
       "electid follows the electtype correction") for old in (4450101, 4450201)],
    *[("retention", {"electid": old}, "electtype", 20, 11,
       "SeatsDataset codes these Utah elections R (uncontested nonpartisan reverted "
       "to retention); the codebook dates that practice to 1968-1984")
      for old in (4402020, 4402120, 4402220, 4402320, 4450120, 4450220)],
    *[("retention", {"electid": old}, "electid", old, old - 9,
       "electid follows the electtype correction; now matches the Election record")
      for old in (4402020, 4402120, 4402220, 4402320, 4450120, 4450220)],
    # --- Montana: Jim Shea's 2020 uncontested (reverted) election
    ("elections", {"electid": 2607501}, "year", 2022, 2020,
     "seat 26075 is 2020 in SeatsDataset and RetentionDataset; Shea's term ran to "
     "January 2021"),
    ("elections", {"electid": 2607501}, "electtype", 1, 11,
     "SeatsDataset codes the seat R (uncontested, reverted to retention), as for "
     "every other unopposed Montana incumbent"),
    ("elections", {"electid": 2607501}, "electid", 2607501, 2607511,
     "electid follows the electtype correction"),
    ("elections", {"electid": 2607111}, "__drop__", None, None,
     "duplicate of 2607011 (Shea, 2016) placed on seat 26071, which is the "
     "Sandefur v. Juras open seat; no Seats or Retention record matches it"),
    ("retention", {"electid": 2607311, "year": 2020}, "electid", 2607311, 2607511,
     "duplicate key: 2607311 is Beth Baker's 2018 election; Shea 2020 is seat "
     "26075, so electid 2607511"),
    # --- Arizona 2022 retention: the three rows repeat the 2020 rows' vote counts,
    # correlation and IDs under the 2022 justices' names.
    *[("retention", {"electid": eid, "year": 2022}, col, old, new, why)
      for eid, sid, nm, yes, no, olds in [
          (306520, 3068, "James Beene", 1305293, 545434, (1865552, 617429, -0.849173)),
          (306620, 3069, "William (Bill) Montgomery", 1042134, 834653, (1683460, 790095, -0.782749)),
          (306720, 3070, "Ann Timmer", 1301858, 529551, (1806530, 679989, -0.765344))]
      for col, old, new, why in [
          ("yes", olds[0], yes, f"2022 row carried the 2020 count; {AZ22}"),
          ("no", olds[1], no, f"2022 row carried the 2020 count; {AZ22}"),
          ("pct_yes", "__any__", round(yes / (yes + no), 6), "recomputed from corrected counts"),
          ("correlation", olds[2], None,
           "2022 row carried the 2020 correlation; the archive has no 2022 county returns"),
          ("seatid", eid // 100, sid, "duplicate key: reused the 2020 seatid; next unused"),
          ("electid", eid, sid * 100 + 20, "duplicate key: follows the new seatid"),
      ]],
    ("retention", {"electid": 306520, "year": 2020}, "name", "Robnert Brutinel",
     "Robert Brutinel", "typo"),
    ("retention", {"electid": 508020}, "YearTookOffice", "202-", 2020,
     "truncated entry; DateAppointed is 2020-12-04"),
    # --- Election rows filed under the wrong state. In each case the candidates
    # and the SeatsDataset record say which state the election belongs to.
    ("elections", {"electid": 1205701}, "state", "AR", "ID",
     "Warren Jones, Idaho 2014; seatid 12057 and stateid 12 are Idaho"),
    *[("elections", {"electid": eid}, col, old, new,
       "O'Brien v. Burke is Illinois 2022, SeatsDataset seat 13063; the IDs used "
       "Kansas's prefix 16")
      for eid, col, old, new in [(1630202, "seatid1", 16302, 13063),
                                 (1630202, "stateid", 16, 13),
                                 (1630202, "electid", 1630202, 1306302)]],
    *[("elections", {"electid": eid}, col, old, new,
       "Aberusturi v. Cadish is the 2018 Nevada primary for SeatsDataset seat 28070 "
       "(Cadish v. Tao); the IDs used Maryland's prefix 20")
      for eid, col, old, new in [(2087005, "seatid1", 20870, 28070),
                                 (2087005, "stateid", 20, 28),
                                 (2087005, "electid", 2087005, 2807005)]],
    ("elections", {"electid": 2087101}, "__drop__", None, None,
     "duplicate of 2807101 (Abbi Silver, Nevada 2018) under Maryland's prefix"),
    ("elections", {"electid": 2807305}, "state", "NM", "NV",
     "Pickering v. Rodriguez is the 2020 Nevada primary (seat 28073); its IDs "
     "were already Nevada's"),
    *[("elections", {"electid": eid}, col, old, new,
       "Lynn Nakamoto, Oregon 2016, SeatsDataset seat 37087; the IDs used Ohio's "
       "prefix 35")
      for eid, col, old, new in [(3508701, "seatid1", 35087, 37087),
                                 (3508701, "stateid", 35, 37),
                                 (3508701, "electid", 3508701, 3708701)]],
    *[("elections", {"electid": eid}, col, old, new,
       "Carpenter v. Pringle, Colorado 1962, is SeatsDataset seat 6018; seatid "
       "4018 is an Arkansas seat")
      for eid, col, old, new in [(401802, "seatid1", 4018, 6018),
                                 (401802, "electid", 401802, 601802)]],
    *[("elections", {"electid": eid}, col, old, new,
       "Leavitt v. Power, Nevada 1998, is SeatsDataset seat 28046; seatid 24046 "
       "is a Mississippi seat")
      for eid, col, old, new in [(2404601, "seatid1", 24046, 28046),
                                 (2404601, "electid", 2404601, 2804601)]],
    *[("elections", {"electid": eid, "year": yr}, col, old, new,
       "seat IDs swapped: SeatsDataset has Saitta on 28065 (2012) and Bell on "
       "28075 (2022)")
      for eid, yr, col, old, new in [(2807501, 2012, "seatid1", 28075, 28065),
                                     (2807501, 2012, "electid", 2807501, 2806501),
                                     (2806501, 2022, "seatid1", 28065, 28075),
                                     (2806501, 2022, "electid", 2806501, 2807501)]],
    # --- Seats
    ("seats", {"seatid": 9501, "year": 1970}, "seatid", 9501, 9502,
     "duplicate key: 9501 is the 1952 Roberts-Lewis seat; the corrected Election "
     "file puts Dekle v. Foster 1970 on seat 9502 (electid 950207)"),
    ("seats", {"seatid": 26077}, "Candidates", "Gufsafson v. Brown",
     "Gustafson v. Brown", "typo"),
]

# ------------------------------------------------------------------ value labels
ELECTTYPE = {1: "general election, nonpartisan", 2: "general election, partisan",
             3: "general election, hybrid",
             4: "general election, run-off (Louisiana after a blanket primary at the general)",
             5: "primary, nonpartisan", 6: "primary, open or blanket", 7: "primary, Democratic",
             8: "primary run-off, Democratic", 9: "primary, Republican",
             10: "primary run-off, Republican",
             11: "general election, uncontested nonpartisan reverted to retention (MT, UT)",
             20: "retention election",
             21: "retention-type election without an incumbent (California confirmation)"}
CANDTYPE = {1: "open seat", 2: "incumbent", 3: "challenger",
            4: "challenger who defeated the incumbent in the primary",
            5: "appointed incumbent chief justice who was formerly an associate justice",
            6: "associate justice running for an open chief justice position",
            7: "associate justice challenging a sitting chief justice",
            8: "challenger who defeated the incumbent at the party convention"}
PARTY = {1: "Democrat", 2: "Republican", 3: "Libertarian", 4: "American Independent",
         5: "Constitution", 6: "Conservative", 7: "Consumer", 8: "Free Liberal", 9: "Green",
         10: "Human Rights", 11: "Labor", 12: "Liberal", 13: "Natural Law", 14: "Patriot",
         15: "Progressive", 16: "Prohibition", 17: "Socialist", 18: "U.S. Taxpayers",
         20: "Independent", 21: "not identified / unclear / other", 22: "write-in",
         23: "none of the above"}
INCUMBENT = {"A": "unopposed appointed incumbent", "AL": "appointed incumbent lost",
             "ALP": "appointed incumbent lost in primary",
             "AT": "appointed incumbent won facing only third-party candidate(s)",
             "AW": "appointed incumbent won",
             "C": "unopposed appointed chief justice who had been an associate justice",
             "CL": "appointed chief justice who had been an associate justice lost",
             "CW": "appointed chief justice who had been an associate justice won",
             "E": "previously elected incumbent unopposed",
             "EL": "previously elected incumbent lost",
             "ELC": "previously elected incumbent denied nomination at party convention",
             "ELP": "previously elected incumbent lost primary",
             "ET": "previously elected incumbent won facing only third-party candidate(s)",
             "EW": "previously elected incumbent won",
             "EW/O(U)": "elected incumbent won Democratic primary then died; primary loser "
                        "ran unopposed in the general (Texas 1982)",
             "O": "open election",
             "OT": "open election, one main-party candidate and third-party candidate(s)",
             "write-ins": "all candidates write-in"}
PRIMARY = {"@P": "nonpartisan primary won with >50%, so no general election",
           "DC": "contested Democratic convention where the incumbent lost",
           "DP": "Democratic primary", "DP&RP": "Democratic and Republican primaries",
           "DP&RP-RO": "both primaries, Republican run-off",
           "DP-RO": "Democratic primary followed by run-off",
           "DP-RO&RP": "both primaries, Democratic run-off",
           "DP-RO&RP-RO": "both primaries, both run-offs",
           "G-RO": "nonpartisan primary at the general, December run-off (GA, MS)",
           "OP": "open primary at the general (Louisiana)",
           "OP-RO": "open primary at the general, December run-off (Louisiana)",
           "P": "nonpartisan primary", "P-RO": "nonpartisan primary followed by run-off",
           "RP": "Republican primary", "RP-RO": "Republican primary followed by run-off"}
LABELS = [
    ("elections", "electtype", ELECTTYPE),
    ("elections", "CourtType", {1: "Supreme Court", 2: "Court of Criminal Appeals (TX, OK)"}),
    ("elections", "CJ", {1: "chief justice seat", 2: "not a chief justice seat"}),
    ("elections", "CandType", CANDTYPE),
    ("elections", "IncumType", {1: "elected", 2: "appointed"}),
    ("elections", "Party", PARTY),
    ("retention", "electtype", {k: ELECTTYPE[k] for k in (11, 20, 21)}),
    ("seats", "BallotFormat", {1: "partisan", 2: "hybrid (party nomination, nonpartisan "
                               "general ballot)", 3: "nonpartisan"}),
    ("seats", "CourtType", {"sc": "Supreme Court", "cr": "Court of Criminal Appeals (TX, OK)"}),
    ("seats", "incumbent", INCUMBENT),
    ("seats", "uncontested", {"R": "uncontested nonpartisan reverted to retention (MT, UT)",
                              "U": "uncontested"}),
    ("seats", "Primary", PRIMARY),
    ("selection", "method", {"partisan": "partisan election", "hybrid": "party nomination, "
                             "nonpartisan general ballot (AZ to 1974, MI, OH to 2020)",
                             "nonpartisan": "nonpartisan election",
                             "retention": "retention election (usually after appointment)"}),
]

STATES = [("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"),
          ("CA", "California"), ("CO", "Colorado"), ("CT", "Connecticut"), ("DE", "Delaware"),
          ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"), ("ID", "Idaho"),
          ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"), ("KS", "Kansas"),
          ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"), ("MD", "Maryland"),
          ("MA", "Massachusetts"), ("MI", "Michigan"), ("MN", "Minnesota"),
          ("MS", "Mississippi"), ("MO", "Missouri"), ("MT", "Montana"), ("NE", "Nebraska"),
          ("NV", "Nevada"), ("NH", "New Hampshire"), ("NJ", "New Jersey"),
          ("NM", "New Mexico"), ("NY", "New York"), ("NC", "North Carolina"),
          ("ND", "North Dakota"), ("OH", "Ohio"), ("OK", "Oklahoma"), ("OR", "Oregon"),
          ("PA", "Pennsylvania"), ("RI", "Rhode Island"), ("SC", "South Carolina"),
          ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"), ("UT", "Utah"),
          ("VT", "Vermont"), ("VA", "Virginia"), ("WA", "Washington"),
          ("WV", "West Virginia"), ("WI", "Wisconsin"), ("WY", "Wyoming")]


def read_xlsx(members, name):
    return pd.read_excel(io.BytesIO(members[name]), sheet_name=0)


def apply_fixes(tables):
    log = []
    for table, key, col, old, new, why in FIXES:
        df = tables[table]
        m = pd.Series(True, index=df.index)
        for k, v in key.items():
            m &= df[k] == v
        if m.sum() != 1:
            raise SystemExit(f"fix {table} {key}: matched {m.sum()} rows, expected 1 -- "
                             "has the source been corrected? review FIXES")
        i = df.index[m][0]
        rid = {k: df.at[i, k] for k in ("electid", "seatid", "year") if k in df}
        if col == "__drop__":
            tables[table] = df.drop(index=i)
            log.append({"table": table, **rid, "column": "(row)", "old": "present",
                        "new": "dropped", "reason": why})
            continue
        cur = df.at[i, col]
        if old != "__any__":
            same = (pd.isna(cur) and old is None) or cur == old or (
                isinstance(old, float) and abs(float(cur) - old) < 1e-6)
            if not same:
                raise SystemExit(f"fix {table} {key} {col}: found {cur!r}, expected {old!r}")
        if new is None and pd.api.types.is_integer_dtype(df[col].dtype):
            df[col] = df[col].astype("Float64")
        if col == "YearTookOffice":
            df[col] = df[col].astype(object)
        df.at[i, col] = new
        log.append({"table": table, **rid, "column": col, "old": cur, "new": new,
                    "reason": why})
    return pd.DataFrame(log)


def tidy(df):
    """-9 -> blank; whole-number float columns -> Int64; dates -> ISO strings."""
    df = df.copy()
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            df[c] = s.dt.strftime("%Y-%m-%d")
            continue
        if s.dtype == object:
            num = pd.to_numeric(s, errors="coerce")
            if num.notna().sum() == s.notna().sum() and s.notna().any():
                s = num
            else:
                continue
        if pd.api.types.is_numeric_dtype(s):
            s = s.mask(s == -9)
            if (s.dropna() % 1 == 0).all():
                s = s.astype("Int64")
            df[c] = s
    return df


def derive_selection(seats, retention):
    """Selection-method spans by state and court, from the elections observed.

    Two layers: the ballot format of contested-or-scheduled seats (SeatsDataset
    BallotFormat: partisan / hybrid / nonpartisan, which counts Montana and Utah
    reverted-to-retention seats as nonpartisan, as they legally were), and
    retention elections (types 20 and 21). For each method the observed years
    split into segments wherever no election of that kind occurred for more
    than SPAN_GAP years *and* another method was observed in between. Each
    segment then runs from its first observed year until the year before the
    next segment of a different method begins -- or to DATA_END if none does
    and the method was still in use within SPAN_GAP years of it; otherwise it
    stops at its last observed election (New York, appointive after 1974) --
    so a switch year is attributed to the old method until the first election
    under the new one. A state's earliest segment is backdated to 1946 when its
    first observed election is 1946-1955 (any state electing then was electing
    in 1946); otherwise it starts at the first observed election."""
    obs = []
    for _, r in seats.iterrows():
        obs.append((r.state, "cr" if r.CourtType == "cr" else "sc", int(r.year),
                    {1: "partisan", 2: "hybrid", 3: "nonpartisan"}[int(r.BallotFormat)]))
    for _, r in retention[retention.electtype.isin([20, 21])].iterrows():
        obs.append((r.state2, "cr" if str(r.circuit).upper() == "CR" else "sc", int(r.year),
                    "retention"))
    obs = pd.DataFrame(obs, columns=["state", "court", "year", "method"])
    rows = []
    for (st, court), g in obs.groupby(["state", "court"]):
        segs = []
        for m, gm in g.groupby("method"):
            yrs = sorted(gm.year.unique())
            others = sorted(g[g.method != m].year.unique())
            cur = [yrs[0]]
            for y in yrs[1:]:
                between = any(cur[-1] < o < y for o in others)
                if y - cur[-1] > SPAN_GAP and between:
                    segs.append((m, cur))
                    cur = [y]
                else:
                    cur.append(y)
            segs.append((m, cur))
        first_any = min(s[1][0] for s in segs)
        for m, yrs in segs:
            nxt = [s[1][0] for s in segs if s[0] != m and s[1][0] > yrs[-1]]
            if nxt:
                end = min(nxt) - 1
            elif yrs[-1] >= DATA_END - SPAN_GAP:
                end = DATA_END
            else:                     # elections stopped (New York after 1974)
                end = yrs[-1]
            start = yrs[0]
            if start == first_any and 1946 <= start <= 1955:
                start = 1946
            n = int(((g.method == m) & g.year.between(yrs[0], yrs[-1])).sum())
            rows.append({"state": st, "court": court, "method": m, "start": start,
                         "end": end, "first_obs": yrs[0], "last_obs": yrs[-1],
                         "n_obs": n})
    return (pd.DataFrame(rows).sort_values(["state", "court", "start", "method"])
            .reset_index(drop=True))


def scdb_state_codes(ref_dir):
    path = os.path.join(ref_dir, "value_labels.csv")
    with open(path, encoding="utf-8") as fh:
        return {r["label"]: int(r["code"]) for r in csv.DictReader(fh)
                if r["variable"] == "caseSourceState"}


def write_gz(df, path):
    buf = io.StringIO()
    df.to_csv(buf, index=False, lineterminator="\n")
    with gzip.GzipFile(path, "wb", mtime=0, compresslevel=9) as g:
        g.write(buf.getvalue().encode("utf-8"))


def write_csv(df, path):
    df.to_csv(path, index=False, lineterminator="\n")


def check(t, sel):
    e, s, r = t["elections"], t["seats"], t["retention"]
    for name, df, k in [("elections", e, "electid"), ("seats", s, "seatid"),
                        ("retention", r, "electid")]:
        d = df[k].duplicated().sum()
        assert d == 0, f"{name}: {d} duplicate {k}"
    sid = {ab: i for i, (ab, _) in enumerate(STATES, 1)}
    for name, df, st, k, div in [("elections", e, "state", "electid", 100000),
                                 ("elections", e, "state", "seatid1", 1000),
                                 ("seats", s, "state", "seatid", 1000),
                                 ("retention", r, "state2", "electid", 100000)]:
        bad = df[(df[st].map(sid) != df.stateid) | (df[k] // div != df.stateid)]
        assert bad.empty, f"{name}: state/stateid/{k} disagree:\n{bad[[st, 'stateid', k]]}"
    assert (e.electid % 100 == e.electtype).all(), "electid suffix != electtype"
    assert (r.electid % 100 == r.electtype).all(), "retention electid suffix != electtype"
    assert (r.electid // 100 == r.seatid).all(), "retention electid != seatid*100+type"
    r11, e11 = r[r.electtype == 11], e[e.electtype == 11]
    assert set(r11.electid) == set(e11.electid), "type-11 records do not pair up"
    pair = r11.merge(e11, on="electid", suffixes=("_r", "_e"))
    assert (pair.year_r == pair.year_e).all(), "type-11 pair years differ"
    yes = r.yes / (r.yes + r.no)
    bad = r[(yes - r.pct_yes).abs() > 0.001]
    assert ((sel.end >= sel.start)).all()
    seat_years = set(zip(s.seatid, s.year))
    unmatched = e[[(a, b) not in seat_years for a, b in zip(e.seatid1, e.year)]]
    return bad, unmatched


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--raw", required=True, help="folder with the archive's .7z files")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    skill = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ref = os.path.join(skill, "references")
    srcs = {k: os.path.join(a.raw, f) for k, f in
            [("all", "AllFiles.7z"), ("elect", "ElectionDataset.7z"),
             ("ret", "RetentionDataset.7z")]}
    allm = un7z.read(srcs["all"])
    t = {"elections": read_xlsx(un7z.read(srcs["elect"]), "ElectionDataset.xlsx"),
         "seats": read_xlsx(allm, "SeatsDataset.xlsx"),
         "retention": read_xlsx(un7z.read(srcs["ret"]), "RetentionDataset.xlsx")}
    if un7z.read(srcs["ret"])["RetentionDataset.xlsx"] != allm["RetentionDataset.xlsx"]:
        print("note: RetentionDataset differs between the two archives; using the standalone one")
    source_rows = {k: len(v) for k, v in t.items()}
    t = {k: tidy(v) for k, v in t.items()}
    log = apply_fixes(t)
    t = {k: tidy(v) for k, v in t.items()}
    sort = {"elections": ["stateid", "year", "electid"], "seats": ["stateid", "year", "seatid"],
            "retention": ["stateid", "year", "electid"]}
    t = {k: v.sort_values(sort[k], kind="stable").reset_index(drop=True) for k, v in t.items()}
    sel = derive_selection(t["seats"], t["retention"])
    flagged, unmatched = check(t, sel)

    codes = scdb_state_codes(ref)
    covered = set(t["elections"].state) | set(t["retention"].state2) | set(t["seats"].state)
    states = pd.DataFrame([{"stateid": i, "state": ab, "state_name": nm,
                            "scdb_state": codes[nm], "in_archive": ab in covered}
                           for i, (ab, nm) in enumerate(STATES, 1)])
    assert (states.set_index("state").stateid
            .reindex(t["elections"].state.unique()).values ==
            t["elections"].groupby("state").stateid.first()
            .reindex(t["elections"].state.unique()).values).all(), "stateid scheme mismatch"

    os.makedirs(a.out, exist_ok=True)
    files = {"elections.csv.gz": t["elections"], "seats.csv.gz": t["seats"],
             "retention.csv.gz": t["retention"]}
    for f, df in files.items():
        write_gz(df, os.path.join(a.out, f))
    write_csv(sel, os.path.join(a.out, "selection.csv"))
    write_csv(states, os.path.join(a.out, "states.csv"))
    write_csv(log, os.path.join(a.out, "fixes.csv"))
    lab = [{"table": tb, "variable": v, "code": k, "label": lbl}
           for tb, v, d in LABELS for k, lbl in d.items()]
    write_csv(pd.DataFrame(lab), os.path.join(ref, "state_value_labels.csv"))

    def digest(p):
        with open(p, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    man = {"source": "Herbert M. Kritzer, State Supreme Court Election Archive, "
                     "updated February 9, 2024 (University of Minnesota Law School)",
           "inputs": {os.path.basename(p): digest(p) for p in srcs.values()},
           "source_tables": {"elections": "ElectionDataset.7z (saved 2024-03-07)",
                             "seats": "AllFiles.7z / SeatsDataset.xlsx (2024-02-10)",
                             "retention": "RetentionDataset.7z"},
           "source_rows": source_rows, "fixes": len(log),
           "flagged_pct_yes": flagged.electid.tolist(),
           "elections_without_seat_year": unmatched.electid.tolist(),
           "selection": {"span_gap": SPAN_GAP, "data_end": DATA_END, "rows": len(sel)}}
    for f in list(files) + ["selection.csv", "states.csv", "fixes.csv"]:
        p = os.path.join(a.out, f)
        df = files.get(f)
        if df is None:
            df = pd.read_csv(p)
        man[f] = {"rows": len(df), "cols": df.shape[1], "sha256": digest(p),
                  "bytes": os.path.getsize(p)}
        if "year" in df:
            man[f]["years"] = [int(df.year.min()), int(df.year.max())]
    with open(os.path.join(a.out, "MANIFEST.json"), "w") as fh:
        json.dump(man, fh, indent=2)
        fh.write("\n")
    for f in files:
        print(f"{f:18s} {man[f]['rows']:>6,} rows  {man[f]['years'][0]}-{man[f]['years'][1]}")
    print(f"selection.csv      {len(sel):>6,} spans   fixes.csv {len(log)} corrections   "
          f"{len(flagged)} retention rows flagged (pct_yes != yes/(yes+no))   "
          f"{len(unmatched)} elections whose seatid has no Seats record that year")


if __name__ == "__main__":
    main()
