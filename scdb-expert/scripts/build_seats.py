"""Build a seat-level panel of the U.S. courts of appeals, 1891-present.

A *seat* is an authorized judgeship. The FJC's Federal Judicial Service file
assigns every appointment an official Seat ID -- CA10103 is First Circuit,
seat 1, third occupant -- and records the statute that created the seat, so
seats and succession chains are looked up, not inferred.

Occupancy runs from the commission date to whichever comes first, senior status
or termination. Taking senior status vacates the authorized judgeship (the judge
keeps hearing cases) and is what lets a successor be appointed; using it as the
end date is what makes occupied seats reconcile to 28 U.S.C. 44.

Judicial Common Space scores are joined from the judge master file by
matchjcs.match. They are appointment-based and time-invariant, so a seat's
ideology is a step function and sometimes does not step at all -- two judges
appointed by the same president from the same state score identically.
Occupancy is the spine; ideology is an attached, nullable attribute.

Outputs, written to --out:
    coa_seats.csv        one row per seat: creating statute, span, occupant count
    coa_seat_spells.csv  one row per occupancy, with predecessor and ideology shift
    coa_seat_years.csv   circuit x seat x year panel

Usage:
    python build_seats.py --fjc federal-judicial-service.csv \
                          --master "judge master base 2026 with jcs.dta" \
                          --out data/coa
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matchjcs

LAST_YEAR = 2026
# Seat ID prefixes -> the circuit numbering used throughout this skill
# (1-11 by number, 12 = D.C., 13 = Federal), matching data/jcs/circuits.csv.
TOK_TO_CIRCUIT = {**{str(i): i for i in range(1, 12)}, "DC": 12, "FC": 13}
CIRCUIT_NAME = {1: "First", 2: "Second", 3: "Third", 4: "Fourth", 5: "Fifth",
                6: "Sixth", 7: "Seventh", 8: "Eighth", 9: "Ninth", 10: "Tenth",
                11: "Eleventh", 12: "D.C.", 13: "Federal"}
# Authorized judgeships today, 28 U.S.C. 44.
STATUTORY = {1: 6, 2: 13, 3: 14, 4: 15, 5: 17, 6: 16, 7: 11, 8: 11, 9: 29,
             10: 12, 11: 12, 12: 11, 13: 12}


def _year(s):
    """Leading four digits of an FJC date string, as a float year."""
    return pd.to_numeric(s.str.slice(0, 4), errors="coerce")


def load_fjc(path):
    f = pd.read_csv(path, dtype=str, keep_default_na=False)
    a = f[f["Court Type"].str.contains("Court of Appeals", case=False)].copy()

    # Seat IDs ending 'SR' are senior judges reassigned when a court was created
    # -- 6 to the Eleventh in 1981 (94 Stat. 1994) and 4 to the Federal Circuit
    # in 1982 (96 Stat. 25). They held no authorized judgeship, so they have no
    # seat number and are excluded from the seat structure.
    a["senior_transfer"] = a["Seat ID"].str.endswith("SR")
    dropped = int(a.senior_transfer.sum())
    a = a[~a.senior_transfer].copy()

    s = a["Seat ID"].str.extract(r"^CA(DC|FC|\d{1,2})(\d{2})(\d{2})$")
    if s[0].isna().any():
        raise SystemExit("unparsed Seat IDs: "
                         f"{sorted(a.loc[s[0].isna(), 'Seat ID'].unique())}")
    a["circuit"] = s[0].map(TOK_TO_CIRCUIT).values
    a["seat_no"] = s[1].astype(int).values
    a["occupancy"] = s[2].astype(int).values
    a["seat_id"] = ("CA" + a.circuit.astype(str).str.zfill(2) + "-"
                    + a.seat_no.astype(str).str.zfill(2))
    a["circuit_name"] = a.circuit.map(CIRCUIT_NAME)
    a["judge_name"] = a["Judge Name"]

    a["start"] = (_year(a["Commission Date"])
                  .fillna(_year(a["Recess Appointment Date"]))
                  .fillna(_year(a["Confirmation Date"])))
    if a.start.isna().any():
        raise SystemExit(f"{int(a.start.isna().sum())} appointments have no usable "
                         "commission, recess or confirmation date")
    a["start"] = a.start.astype(int)
    a["senior_year"] = _year(a["Senior Status Date"])
    a["termination_year"] = _year(a["Termination Date"])
    a["end"] = a[["senior_year", "termination_year"]].min(axis=1)
    a["sitting"] = a.end.isna()
    a["creating_statute"] = a["Statute Authorizing New Seat"].str.strip().replace("", np.nan)
    a["president"] = a["Appointing President"]
    a["pres_party"] = a["Party of Appointing President"].replace("", np.nan)
    a["left_because"] = a["Termination"].replace("", np.nan)
    a.attrs["senior_transfers_dropped"] = dropped
    return a.sort_values(["circuit", "seat_no", "occupancy"],
                         kind="stable").reset_index(drop=True)


def load_scores(path=None):
    """Judge-level JCS scores, as (frame, year_tol).

    With no path, the skill's own bundled `jcs("coa")` table is used: 705 rows,
    703 scored, already public and identical to the research master on every
    judge checked. It carries no confirmation year, so matching falls back to
    name plus circuit (`year_tol=None`), and no home state, so `state` comes
    back empty. Pass a Stata master with YearConfirm, jcs_2024 and state_abbrev
    to use that instead and get both back."""
    if path is None:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import scdb
        d = scdb.jcs("coa")[["name", "circuit", "jcs"]].copy()
        d["state"] = pd.Series([np.nan] * len(d), dtype="object")
        return d.reset_index(drop=True), None
    d = pd.read_stata(path, convert_categoricals=False)
    # Rows without a circuit are Supreme Court justices, who hold no CoA seat.
    d = d[d.circuit.notna()].copy()
    d["circuit"] = d.circuit.astype(int)
    d["jcs"] = d.jcs_2024
    # ZUSA is the master's code for no home state: the D.C. and Federal Circuits
    # are nationwide courts whose seats are not tied to a state.
    d["state"] = d.state_abbrev.replace({"": np.nan, "ZUSA": np.nan})
    return d.reset_index(drop=True), 2    # matchjcs returns labels into this frame


def occupancy_bounds(a):
    """Close each occupancy when the next occupant arrives, so spells on a seat
    never overlap. A real gap is left as a gap, which is a vacant seat."""
    s = a.sort_values(["seat_id", "occupancy"], kind="stable").copy()
    g = s.groupby("seat_id", sort=False)
    nxt = g.start.shift(-1)
    cap = s.end.fillna(LAST_YEAR)
    s["occ_start"] = s.start
    s["occ_end"] = np.where(nxt.notna(), np.minimum(cap, nxt - 1),
                            np.minimum(cap, LAST_YEAR))
    s["occ_end"] = np.maximum(s.occ_end, s.occ_start).astype(int)
    s["predecessor"] = g.judge_name.shift()
    s["pred_jcs"] = g.jcs.shift()
    s["jcs_shift"] = s.jcs - s.pred_jcs
    s["vacancy_years"] = (s.start - g.end.shift()).astype("Float64")
    return s


def seat_years(sp):
    """Expand spells into one row per seat-year."""
    rep = (sp.occ_end - sp.occ_start + 1).astype(int)
    p = sp.loc[sp.index.repeat(rep)].copy()
    p["year"] = p.occ_start + p.groupby(level=0).cumcount()
    cols = ["circuit", "circuit_name", "seat_no", "seat_id", "year", "judge_name",
            "state", "jcs", "pres_party", "president", "occupancy",
            "creating_statute", "jcs_match"]
    return (p[cols].sort_values(["circuit", "seat_no", "year"], kind="stable")
            .reset_index(drop=True))


def seat_registry(sp):
    g = sp.groupby(["circuit", "circuit_name", "seat_no", "seat_id"], as_index=False)
    r = g.agg(created_by=("creating_statute", "first"),
              first_year=("occ_start", "min"), last_year=("occ_end", "max"),
              occupants=("occupancy", "max"), filled_now=("sitting", "any"))
    return r.sort_values(["circuit", "seat_no"]).reset_index(drop=True)


SPELL_COLS = ["circuit", "circuit_name", "seat_no", "seat_id", "occupancy",
              "judge_name", "state", "jcs", "jcs_match", "predecessor", "pred_jcs",
              "jcs_shift", "vacancy_years", "start", "senior_year",
              "termination_year", "end", "occ_start", "occ_end", "sitting",
              "president", "pres_party", "left_because", "creating_statute"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fjc", required=True,
                    help="FJC Federal Judicial Service export (CSV)")
    ap.add_argument("--master", default=None,
                    help="optional Stata master with JCS scores and home states; "
                         "omit to use the skill's bundled jcs(\"coa\") table")
    ap.add_argument("--out", default=".", help="output directory")
    ap.add_argument("--year-tol", type=int, default=None,
                    help="override the confirmation-year tolerance for name matching")
    a = ap.parse_args()

    fjc = load_fjc(a.fjc)
    master, default_tol = load_scores(a.master)
    tol = a.year_tol if a.year_tol is not None else default_tol
    print(f"scores: {'bundled jcs(\"coa\")' if a.master is None else a.master}"
          f"   {len(master)} judges, year guard "
          f"{'off' if tol is None else chr(177) + str(tol)}")
    midx, method = matchjcs.match(fjc, master, year_tol=tol)
    fjc["jcs_match"] = method.values
    ok = midx.notna()
    fjc["jcs"] = np.nan
    fjc["state"] = pd.Series([np.nan] * len(fjc), dtype="object")
    for col in ("jcs", "state"):
        fjc.loc[ok.values, col] = master.loc[midx[ok].astype(int).values, col].values

    sp = occupancy_bounds(fjc)
    panel = seat_years(sp)
    registry = seat_registry(sp)

    os.makedirs(a.out, exist_ok=True)
    registry.to_csv(os.path.join(a.out, "coa_seats.csv"), index=False)
    sp[SPELL_COLS].to_csv(os.path.join(a.out, "coa_seat_spells.csv"), index=False)
    panel.to_csv(os.path.join(a.out, "coa_seat_years.csv"), index=False)

    print(f"appointments: {len(fjc)}   seats: {fjc.seat_id.nunique()}   "
          f"seat-years: {len(panel)}")
    print(f"senior-transfer rows excluded: {fjc.attrs['senior_transfers_dropped']}")
    amb = int(fjc.jcs_match.str.startswith("ambiguous").sum())
    print(f"JCS joined: {int(fjc.jcs.notna().sum())} "
          f"({100 * fjc.jcs.notna().mean():.1f}%)   ambiguous: {amb}")
    for lo, hi in [(1891, 1949), (1950, 1989), (1990, LAST_YEAR)]:
        g = fjc[fjc.start.between(lo, hi)]
        print(f"  {lo}-{hi}: {int(g.jcs.notna().sum())}/{len(g)} "
              f"({100 * g.jcs.notna().mean():.1f}%)")
    print()
    print("occupied seats in 2025 vs authorized judgeships (28 U.S.C. 44):")
    print(f"  {'circuit':<10}{'seats ever':>11}{'2025':>6}{'authorized':>12}{'diff':>6}")
    occ = panel[panel.year == 2025].groupby("circuit").size()
    for c in sorted(fjc.circuit.unique()):
        ever = fjc[fjc.circuit == c].seat_no.nunique()
        now = int(occ.get(c, 0))
        print(f"  {CIRCUIT_NAME[c]:<10}{ever:>11}{now:>6}{STATUTORY[c]:>12}"
              f"{now - STATUTORY[c]:>+6}")
    tot = int(occ.sum())
    print(f"  {'TOTAL':<10}{fjc.seat_id.nunique():>11}{tot:>6}"
          f"{sum(STATUTORY.values()):>12}{tot - sum(STATUTORY.values()):>+6}")
    print()
    print(f"wrote coa_seats.csv, coa_seat_spells.csv, coa_seat_years.csv to {a.out}")


if __name__ == "__main__":
    main()
