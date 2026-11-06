#!/usr/bin/env python3
"""
Build the interactive "majority coalitions" page from the bundled SCDB data.

    python build_coalition_page.py --start 2005 --end 2025 --out coalitions.html

One self-contained HTML file: a force-directed graph in which each node is a set of
justices who formed the majority, sized by how many cases that coalition decided and
coloured by the liberal/conservative mix of those outcomes. Clicking a node lists the
cases. Filters: term, natural court, justice membership, minimum case count.

Coalition rule: a coalition is the set of justices in the majority (`majority == 2`).
A justice who did not participate, or a vacant seat, is simply not in it -- nothing is
imputed, so a 5-3 decided during a vacancy groups with 5-4s having the same five.

Sample: orally argued, formally decided cases (decisionType 1, 6, 7) and merits votes
(vote 1-5), the skill's defaults; see references/analysis_guide.md.

Justices are ordered liberal -> conservative by their liberal vote share within the
selected terms, which is what the membership ring and the chips use.
"""
import argparse, json, os, re, sys
from collections import Counter
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scdb  # noqa: E402

TEMPLATE = os.path.join(HERE, "templates", "coalition_page.html")
# justiceName -> (initials, surname) where the regex below cannot split it
NAME_FIX = {"SDOConnor": ("SD", "O'Connor"), "WVanDevanter": ("W", "Van Devanter")}
ROMAN = {1: "I", 2: "II", 3: "III"}
ACRONYMS = {"Llc": "LLC", "Lp": "LP", "Llp": "LLP", "Usa": "USA", "Us": "US", "Fbi": "FBI", "Nlrb": "NLRB",
            "Sec": "SEC", "Fcc": "FCC", "Epa": "EPA", "Irs": "IRS", "Ftc": "FTC", "Fec": "FEC", "Ii": "II",
            "Iii": "III", "Bnsf": "BNSF", "Nrc": "NRC", "Hhs": "HHS", "Ssa": "SSA", "Tva": "TVA", "Geo": "GEO",
            "Dhs": "DHS", "Nvidia": "NVIDIA", "Pllc": "PLLC", "Ncaa": "NCAA", "Afscme": "AFSCME", "At&T": "AT&T",
            "Ibm": "IBM", "Aig": "AIG", "Pga": "PGA", "Fda": "FDA", "Nasa": "NASA", "Dea": "DEA", "Atf": "ATF",
            "Nra": "NRA", "Nrsc": "NRSC", "Cc": "CC", "Cnh": "CNH"}
SMALL = {"Of", "The", "And", "For", "In", "On", "At", "To", "By", "A", "An", "As", "From", "With", "Its"}


def parse_name(justice_name):
    """'KBJackson' -> ('KB', 'Jackson', ''); 'JHarlan2' -> ('J', 'Harlan', '2')."""
    ordinal = re.search(r"(\d*)$", justice_name).group(1)
    core = justice_name[:len(justice_name) - len(ordinal)]
    if core in NAME_FIX:
        return (*NAME_FIX[core], ordinal)
    m = re.match(r"^([A-Z]*?)([A-Z][a-z].*)$", core)
    return (m.group(1), m.group(2), ordinal) if m else ("", core, ordinal)


def display_names(justice_names):
    """Map justiceName -> display name: the surname alone, with initials (then an
    ordinal) added only where surnames collide within the selected terms. Keeps the
    two Jacksons, Whites, Marshalls, Chases etc. distinct without hand-maintaining a
    list, leaves every unambiguous name short, and always carries SCDB's ordinal
    (Harlan I / Harlan II) since that is how those justices are conventionally named."""
    parsed = {j: parse_name(j) for j in justice_names}
    by_surname = Counter(sur for _, sur, _ in parsed.values())
    out = {}
    for j, (ini, sur, ordinal) in parsed.items():
        if ordinal:                                  # SCDB numbers these: Harlan I / Harlan II
            out[j] = f"{sur} {ROMAN.get(int(ordinal), ordinal)}"
        else:
            out[j] = sur if by_surname[sur] == 1 or not ini else f"{'.'.join(ini)}. {sur}"
    clashing = {n for n, k in Counter(out.values()).items() if k > 1}
    for j, (ini, sur, ordinal) in parsed.items():
        if out[j] in clashing:                       # same surname and initials
            out[j] = f"{sur} ({j})"
    return out


def pretty(name):
    out = []
    for i, w in enumerate(str(name).title().split(" ")):
        core = w.strip(",.")
        if core == "V":
            w = w.replace("V", "v")
        elif core in ACRONYMS:
            w = w.replace(core, ACRONYMS[core])
        elif core in SMALL and i > 0:
            w = w.lower()
        out.append(w)
    return re.sub(r"(’|')S\b", lambda m: m.group(1) + "s", " ".join(out))


def build(start, end, title, heading):
    cases_df = scdb.formally_decided(scdb.load("case"))
    cases_df = cases_df[cases_df.term.between(start, end)].copy()
    if cases_df.empty:
        sys.exit(f"no formally decided cases in terms {start}-{end}")
    cases_df["cite"] = scdb.best_cite(cases_df)
    cases_df = scdb.label(cases_df, ["issueArea", "decisionDirection", "caseDisposition"])
    votes = scdb.merits_votes(scdb.load("justice"))
    votes = votes[votes.term.between(start, end) & votes.caseId.isin(cases_df.caseId)]

    all_rows = scdb.load("justice")
    all_rows = all_rows[all_rows.term.between(start, end)]
    names = display_names(sorted(set(all_rows.justiceName) | set(votes.justiceName)))

    # order justices liberal -> conservative by liberal share in this window
    lib = (votes.groupby("justiceName")
                .apply(lambda d: (d.direction == 2).sum() / max((d.direction.notna()).sum(), 1),
                       include_groups=False)
                .sort_values(ascending=False))
    order = [names[j] for j in lib.index]
    rank = {j: i for i, j in enumerate(order)}

    seats = {int(t): sorted((names[j] for j in d.justiceName.unique()),
                            key=lambda x: rank.get(x, 99))
             for t, d in all_rows.groupby("term")}

    idx = cases_df.set_index("caseId")
    jname = pd.read_csv(os.path.join(scdb.REF, "justices.csv")).set_index("justice").justiceName
    out = []
    for cid, d in votes.groupby("caseId"):
        c = idx.loc[cid]
        maj = sorted((names[j] for j in d.justiceName[d.majority == 2]), key=lambda x: rank[x])
        dis = sorted((names[j] for j in d.justiceName[d.majority == 1]), key=lambda x: rank[x])
        seen = set(maj) | set(dis)
        w = c.majOpinWriter
        txt = lambda x: x if isinstance(x, str) else ""
        out.append(dict(
            id=cid, term=int(c.term), court=int(c.naturalCourt), name=pretty(c.caseName),
            cite=txt(c.cite), date=c.dateDecision.strftime("%b %-d, %Y"),
            sort=c.dateDecision.strftime("%Y-%m-%d"),
            margin=f"{int(c.majVotes)}-{int(c.minVotes)}",
            issue=txt(c.issueArea_label) or "not coded",
            direction=txt(c.decisionDirection_label) or "not coded",
            disposition=txt(c.caseDisposition_label),
            author=names.get(jname[int(w)], "") if pd.notna(w) else "per curiam",
            chief=str(c.chief),
            maj=maj, dis=dis, absent=[j for j in seats[int(c.term)] if j not in seen],
            key="|".join(maj)))

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
                           terms=sorted({x["term"] for x in sel}),
                           first=min(x["sort"] for x in sel), last=max(x["sort"] for x in sel)))

    chiefs = []
    for ch in sorted({x["chief"] for x in out}, key=lambda ch: min(x["term"] for x in out if x["chief"] == ch)):
        sel = [x for x in out if x["chief"] == ch]
        chiefs.append(dict(name=ch, n=len(sel), terms=sorted({x["term"] for x in sel}),
                           courts=[c["code"] for c in courts if c["chief"] == ch]))

    rel = ", ".join(scdb.manifest()["releases"])
    data = dict(order=order, terms=sorted(seats), seats=seats, courts=courts, chiefs=chiefs, cases=out,
                source=f"SCDB {rel}; orally argued, formally decided cases (decisionType 1, 6, 7); "
                       f"majority = voted with the disposition")
    page = open(TEMPLATE, encoding="utf-8").read()
    page = (page.replace("__DATA__", json.dumps(data))
                .replace("__TITLE__", title)
                .replace("__HEADING__", heading))
    return page, data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=2005)
    ap.add_argument("--end", type=int, default=2025)
    ap.add_argument("--title", default=None)
    ap.add_argument("--heading", default=None)
    ap.add_argument("--out", default="scotus_coalitions.html")
    a = ap.parse_args()
    title = a.title or f"Supreme Court majority coalitions, OT{a.start}\u2013OT{a.end}"
    page, data = build(a.start, a.end, title, a.heading or title)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"{a.out}: {len(data['cases'])} cases, "
          f"{len({c['key'] for c in data['cases']})} coalitions, "
          f"{len(data['courts'])} natural courts, {len(data['chiefs'])} chief justices, "
          f"{len(page)/1024:.0f} KB")


if __name__ == "__main__":
    main()
