#!/usr/bin/env python3
"""
Build the "coalitions ranked by majority ideology" page from the bundled SCDB + JCS data.

    python build_coalition_ranking.py --start 1946 --end 2022 --out ranking.html

One self-contained HTML file. Every majority coalition is a row, ranked by the median
Judicial Common Space score of the justices in it: liberal majorities at the top,
conservative at the bottom. Each row shows who was in the coalition (a membership
strip, ordered liberal -> conservative), the spread of its per-case medians, and how
many cases it decided. Clicking a row lists those cases.

Ideology: JCS justice scores (Martin-Quinn mapped into the DW-NOMINATE Common Space by
Epstein, Martin, Segal & Westerland 2007), which run OT1937-OT2022 -- so the end term
is capped there. Raw Martin-Quinn scores are not bundled; within a term the two rank
justices identically, since the JCS mapping is monotone.

Median rule: a coalition's position is the median over its cases of the per-case median
JCS of the majority. Computing per case first keeps each case on that term's scores,
and the min-max bar shows how far the coalition drifted across terms.

Sample: orally argued, formally decided cases (decisionType 1, 6, 7) and merits votes
(vote 1-5); a coalition is the set of justices who voted with the disposition.
"""
import argparse, json, os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scdb  # noqa: E402
from build_coalition_page import display_names, pretty  # noqa: E402

TEMPLATE = os.path.join(HERE, "templates", "coalition_ranking.html")


def jcs_last_term():
    """Last term the bundled JCS data can place a coalition in: it needs both a justice
    score for everyone in the majority and a Court median to compare against. Derived
    from the data, so a newer JCS release extends the page without touching this file."""
    m = scdb.jcs("medians")
    return int(min(scdb.jcs("justice").term.max(), m.loc[m.sc_median.notna(), "term"].max()))


def build(start, end, title, heading):
    end = min(end, jcs_last_term())
    cases_df = scdb.formally_decided(scdb.load("case"))
    cases_df = cases_df[cases_df.term.between(start, end)].copy()
    if cases_df.empty:
        sys.exit(f"no formally decided cases in terms {start}-{end}")
    cases_df["cite"] = scdb.best_cite(cases_df)
    cases_df = scdb.label(cases_df, ["issueArea", "decisionDirection", "caseDisposition"])

    votes = scdb.merits_votes(scdb.load("justice"))
    votes = votes[votes.term.between(start, end) & votes.caseId.isin(cases_df.caseId)]
    votes = scdb.add_jcs(votes)

    all_rows = scdb.load("justice")
    all_rows = all_rows[all_rows.term.between(start, end)]
    names = display_names(sorted(set(all_rows.justiceName) | set(votes.justiceName)))

    lib = (votes.groupby("justiceName")
                .apply(lambda d: (d.direction == 2).sum() / max((d.direction.notna()).sum(), 1),
                       include_groups=False)
                .sort_values(ascending=False))
    order = [names[j] for j in lib.index]
    rank = {j: i for i, j in enumerate(order)}

    seats = {int(t): sorted((names[j] for j in d.justiceName.unique()),
                            key=lambda x: rank.get(x, 99))
             for t, d in all_rows.groupby("term")}

    med = votes[votes.majority == 2].groupby("caseId").jcs.median()
    idx = cases_df.set_index("caseId")
    jname = pd.read_csv(os.path.join(scdb.REF, "justices.csv")).set_index("justice").justiceName
    txt = lambda x: x if isinstance(x, str) else ""
    out, dropped = [], 0
    for cid, d in votes.groupby("caseId"):
        if pd.isna(med.get(cid)):
            dropped += 1
            continue
        c = idx.loc[cid]
        maj = sorted((names[j] for j in d.justiceName[d.majority == 2]), key=lambda x: rank[x])
        dis = sorted((names[j] for j in d.justiceName[d.majority == 1]), key=lambda x: rank[x])
        seen = set(maj) | set(dis)
        w = c.majOpinWriter
        out.append(dict(
            id=cid, term=int(c.term), court=int(c.naturalCourt), chief=str(c.chief),
            name=pretty(c.caseName), cite=txt(c.cite),
            date=c.dateDecision.strftime("%b %-d, %Y"), sort=c.dateDecision.strftime("%Y-%m-%d"),
            margin=f"{int(c.majVotes)}-{int(c.minVotes)}",
            issue=txt(c.issueArea_label) or "not coded",
            direction=txt(c.decisionDirection_label) or "not coded",
            disposition=txt(c.caseDisposition_label),
            author=names.get(jname[int(w)], "") if pd.notna(w) else "per curiam",
            maj=maj, dis=dis, absent=[j for j in seats[int(c.term)] if j not in seen],
            key="|".join(maj), med=round(float(med[cid]), 4)))

    nc = pd.read_csv(os.path.join(scdb.REF, "natural_courts.csv")).set_index("naturalCourt")
    labels = scdb.labels("naturalCourt")
    courts = []
    for code in sorted({x["court"] for x in out}):
        sel = [x for x in out if x["court"] == code]
        roster = sorted((names[j] for j in str(nc.loc[code, "participants"]).split()
                         if j in names and names[j] in rank), key=lambda x: rank[x])
        courts.append(dict(code=code, label=labels[code], n=len(sel), roster=roster,
                           chief=max({x["chief"] for x in sel},
                                     key=lambda ch: sum(1 for x in sel if x["chief"] == ch)),
                           terms=sorted({x["term"] for x in sel})))
    chiefs = []
    for ch in sorted({x["chief"] for x in out}, key=lambda ch: min(x["term"] for x in out if x["chief"] == ch)):
        sel = [x for x in out if x["chief"] == ch]
        chiefs.append(dict(name=ch, n=len(sel), terms=sorted({x["term"] for x in sel}),
                           courts=[c["code"] for c in courts if c["chief"] == ch]))

    m = scdb.jcs("medians").dropna(subset=["term"])
    court_median = {int(r.term): round(float(r.sc_median), 4)
                    for r in m.itertuples() if start <= int(r.term) <= end and pd.notna(r.sc_median)}

    scdb_last = int(scdb.manifest()["case"]["terms"][1])
    later = int((scdb.formally_decided(scdb.load("case")).term > end).sum())
    rel = ", ".join(scdb.manifest()["releases"])
    data = dict(order=order, terms=sorted(seats), seats=seats, courts=courts, chiefs=chiefs,
                courtMedian=court_median, cases=out,
                source=f"SCDB {rel}; orally argued, formally decided cases (decisionType 1, 6, 7). "
                       f"Ideology: Judicial Common Space justice scores (Martin-Quinn mapped into the "
                       f"Common Space; Epstein, Martin, Segal & Westerland 2007), OT{start}-OT{end}. "
                       + (f"The SCDB runs through OT{scdb_last}; the {later} argued cases after OT{end} "
                          f"have no JCS scores yet and are left out." if later else ""))
    page = (open(TEMPLATE, encoding="utf-8").read()
            .replace("__DATA__", json.dumps(data))
            .replace("__TITLE__", title).replace("__HEADING__", heading))
    return page, data, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=1946)
    ap.add_argument("--end", type=int, default=9999)
    ap.add_argument("--title", default=None)
    ap.add_argument("--heading", default=None)
    ap.add_argument("--out", default="scotus_coalition_ranking.html")
    a = ap.parse_args()
    end = min(a.end, jcs_last_term())
    title = a.title or f"Supreme Court coalitions by majority ideology, OT{a.start}–OT{end}"
    page, data, dropped = build(a.start, a.end, title, a.heading or title)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"{a.out}: {len(data['cases'])} cases, {len({c['key'] for c in data['cases']})} coalitions, "
          f"{len(data['courts'])} natural courts, {dropped} dropped for missing scores, "
          f"{len(page)/1024:.0f} KB")


if __name__ == "__main__":
    main()
