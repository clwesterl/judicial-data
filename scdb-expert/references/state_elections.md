# State supreme court elections (Kritzer's archive)

Read this for any question about state judicial elections: who ran, who won, how
close it was, retention votes and defeats, how a state chooses its high court
and when that changed, partisanship in judicial elections, or whether the state
court whose decision the Supreme Court reviewed was elected.

## What's bundled

Herbert M. Kritzer's **State Supreme Court Election Archive** (University of
Minnesota Law School; updated February 9, 2024), the data behind *Justices on the
Ballot* (Cambridge, 2015). The archive is meant to cover every state supreme
court election from 1946 on, in the 39 states that used elections at some point
since then. Coverage runs back to 1936 for California retention votes and
1942 for Missouri. In Texas and Oklahoma it also covers the Court of Criminal
Appeals, which is the court of last resort for criminal cases there.

| table (`data/state/`) | rows | unit | years |
|---|---|---|---|
| `elections.csv.gz` | 2,672 | one election: a contested primary or run-off, or a general election (contested or not); candidates in wide form | 1946–2023 |
| `seats.csv.gz` | 2,302 | one seat up for a partisan, hybrid or nonpartisan election, with competitiveness measures | 1945–2023 |
| `retention.csv.gz` | 896 | one retention-type vote | 1936–2022 |
| `selection.csv` | 68 | **derived here**: a span of years over which a state chose its high court one way | 1936–2023 |
| `states.csv` | 50 | Kritzer `stateid` ↔ postal code ↔ SCDB `caseSourceState` | |
| `fixes.csv` | 76 | every correction this build made to the archive | |

The 11 states with no supreme court elections since 1946 (CT, DE, HI, MA, ME,
NH, NJ, RI, SC, VA, VT) appear only in `states.csv`, with `in_archive = False`.
New York's data stop in 1974, when it moved to appointment.

```python
e  = scdb.state_elections("elections")      # also "seats", "retention", "selection",
                                            #   "states", "fixes"
k  = scdb.state_candidates()                # one row per candidate (derived, 5,470 rows)
scdb.find_state_judge("durham")             # every election a judge stood in
scdb.state_selection("NC")                  # NC's spans; ("NC", 2010) -> ['nonpartisan']
c  = scdb.add_state_selection(scdb.load("case"))   # SCDB + how the state court was chosen
scdb.label_state(e, table="elections")      # <var>_label columns; scdb.state_labels("Party")
```

```bash
python scripts/scdb.py state AZ             # selection history, counts by election type
python scripts/scdb.py state "rose bird"    # every election a justice stood in
```

## Keys and how the tables fit together

- **`seatid`**: the first one or two digits are the `stateid` (1 Alabama … 50
  Wyoming, alphabetical among the 50 states), followed by three digits for the
  seat. In states that have used both retention and some other kind of
  election, retention seats are numbered from 501. A seatid identifies a
  **seat in a given election year**, not a judgeship that persists across
  years.
- **`electid`** = `seatid × 100 + electtype`. Every electid ends in its own
  electtype code (the build checks this).
- **The tables name the state differently.** Elections and seats use `state`
  (postal code). Retention uses `state2` (postal code) and `state_name`, and its
  `state` column is a 1–20 sequence over the retention states. `stateid` is
  the same in all three tables. The loaders keep the archive's names.
- **Elections vs seats.** Elections has one row per *contest*, so a single seat
  can have up to five: Republican primary, Republican run-off, Democratic
  primary, Democratic run-off, and the general election. Seats has one row per
  *seat*. A multi-seat election (two or three seats filled at once, with the top
  vote-getters winning) is one Elections row (`numseats` > 1, `seatid1`–`seatid3`)
  and several Seats rows. For those, Kritzer paired the top vote-getter with
  the lowest, the second with the second-lowest, and so on (in partisan and
  hybrid elections, top Democrat with lowest Republican). Use Elections to
  handle multi-seat contests another way.
- Elections includes a primary or run-off only if it was contested. If a
  primary decided the seat, there is no general-election row.
- **Montana and Utah** elections where an unopposed incumbent faced a yes/no vote
  (`electtype` 11; Montana since 1974, Utah 1968–1984) appear in **all three
  tables**, sharing one electid between Elections and Retention: 28 elections.
  When combining Retention with Seats or Elections, decide whether to count
  them once or twice. Kritzer's suggested approach: Retention + Seats when the
  unit is the seat, Retention + Elections when it is every distinct election.
- 66 Seats rows have no Elections row. 46 are uncontested seats in states that
  leave uncontested races off the ballot. The other 20 are contested seats
  whose Elections record is missing or filed under another seat (for example,
  Pennsylvania 2021 and 2023, and several Michigan years), so **Seats is the
  more complete list of contested seats.**

## Codes that matter

Every code is in `references/state_value_labels.csv` (`table, variable, code,
label`).

- **Four kinds of election** (Kritzer's terms):
  - **partisan**: party nominees on the general ballot (including Louisiana's
    blanket primary);
  - **hybrid**: party nomination by primary or convention, then a nonpartisan
    general ballot (Arizona to 1974, Michigan, Ohio to 2020);
  - **nonpartisan**;
  - **retention**: a yes/no vote, almost always on a sitting justice. In
    California an open seat can be filled by a single nominee subject to a
    confirmation vote (`electtype` 21, 1990 and 2014).
- `electtype` (Elections): 1–4 general elections, 5–10 primaries and run-offs,
  11 uncontested nonpartisan reverted to retention. Retention uses 11, 20 and 21.
- `CandType`*X* separates incumbents (2) from open-seat (1) and challenger (3,
  4, 8) candidates, and flags chief-justice races (5–7). `IncumType`*X*: 1
  elected, 2 appointed. To isolate an appointed justice's first election, use
  `IncumType` = 2.
- `Party`*X* is coded only in partisan and hybrid general elections. Code 23 is
  Nevada's "none of the above," and `numcandidates` counts it as a candidate.
- Seats `incumbent` combines who ran with how they did (for example AW =
  appointed incumbent won, ELP = elected incumbent lost the primary).
  `uncontested` is R (reverted to retention) or U. `Primary` describes which
  primaries were held.
- **Seats `Pct*` are percentages (0–100)**, the incumbent's (or the winner's)
  share of the two-candidate vote. `Vote*` are the corresponding vote ratios:
  `Pct = 100 × Vote / (1 + Vote)` exactly. Retention `pct_yes` is a proportion
  (0–1).
- Elections `First`, `Second`, `VoteRatio` (not in the codebook): the top two
  vote totals and their ratio.
- **CourtType is coded three ways.** Elections: 1 Supreme Court, 2 Court of
  Criminal Appeals. Seats: lowercase `sc`/`cr`, blank outside Texas and
  Oklahoma. Retention: `circuit` holds `SC`/`CR` for Oklahoma, the district for
  Illinois, Maryland and Nebraska (where retention is by district), and `CJ`
  for Nebraska's statewide chief-justice vote.

### The partisan correlation

`correlation` is a county-level correlation between the judicial vote and the
Democratic share of the gubernatorial vote (in Alaska, by election district).
The judicial vote is the yes share in a retention election, the Democrat's
share in a partisan election, the Democratic nominee's share in a hybrid
election, and either candidate's share in a nonpartisan election.
**Nonpartisan correlations are absolute values**: Kritzer did not link
nonpartisan candidates to parties. So a nonpartisan correlation measures how
partisan the vote pattern was, not its direction. Compare its magnitude with
other kinds of election, never its sign.

When no gubernatorial election was held at the same time, Kritzer averaged the
governor's races before and after. Where one was a year away, the nearer race
was weighted ¾. Wisconsin's April elections are paired with the adjacent
November. Correlations are missing for district-based elections. For the
newest elections, Kritzer computed them from the preceding governor's race
only.

### Retention defeats are in `notes`

The `notes` field records the 12 justices who were not retained. Look there
rather than at `pct_yes < 0.5`, because thresholds differ: Illinois requires
60% yes (Kilbride lost in 2020 with 56.5%), and New Mexico requires 57%. The
defeats are AK 1964; CA 1986 (Bird, Grodin, Reynoso); IA 2010 (three
justices); NE 1996; PA 2005; TN 1996; WY 1992; IL 2020.

## What the build corrected

The archive arrives as Excel files inside `.7z` archives
(`state-elections-raw/`). `scripts/build_state_elections.py` reads them with
`scripts/un7z.py`, a standard-library 7z reader, so no 7-Zip install is
needed. **Which file each table comes from matters.**
`ElectionDataset.7z` (saved 2024-03-07) is a corrected version of the copy
inside `AllFiles.7z` (saved 2024-02-09). The AllFiles copy has 39 duplicated
electids that the standalone file resolves, so the build uses the standalone
file. Seats exists only in AllFiles. The two copies of Retention are
byte-identical.

Two conversions apply throughout: the archive's `-9` missing-value code becomes
blank, and dates become ISO `yyyy-mm-dd`. Beyond that, `fixes.csv` lists all 76
corrections, each with its old value, new value and reason. Each fix in the build
script asserts the value it replaces, so a future release that has fixed the
problem stops the build instead of being double-corrected. The corrections fall
into five groups:

1. **Arizona 2022 retention.** The three 2022 rows (Beene, Montgomery, Timmer)
   repeated the 2020 rows' yes/no counts, correlations and IDs; the 2020
   workbook block had been copied and only the names changed. The counts are
   replaced with statewide canvass totals from Ballotpedia, whose 2020 Arizona
   figures match the archive exactly. Correlations are set to blank because the
   archive has no 2022 county returns. The rows get new seats 3068–3070.
2. **Election rows filed under the wrong state.** Eight rows had another
   state's postal code, `stateid` or seat number. For example, Illinois's 2022
   O'Brien v. Burke used Kansas's prefix, and Nevada and Oregon rows used
   Maryland's and Ohio's. One of the eight was a duplicate and is dropped.
   Separately, Nevada's 2012 and 2022 rows for Saitta and Bell had their seat
   IDs swapped. Seats identifies the right record in every case.
3. **Montana and Utah reverted-retention elections**, made consistent across
   the three tables. Utah's were coded with an undocumented `electtype` 14 in
   Elections and as 20 in Retention for 1978–84. Seats and the codebook both
   say 11. Two year errors (Durham 1980 → 1982; Shea 2022 → 2020) and one
   duplicate (Shea 2016 placed on another seat) are fixed or dropped.
4. **Duplicate keys**: Montana `electid` 2607311 (Baker 2018 / Shea 2020) and
   Seats `seatid` 9501 (Florida 1952 / 1970).
5. **Typos**: "Robnert" Brutinel, "Gufsafson", and a `YearTookOffice` entered
   as "202-".

After these corrections the build checks that every key is unique; that
state, stateid, seatid and electid agree in every row; that every electid
ends in its electtype; and that the 28 type-11 elections pair up exactly
between Elections and Retention, with the same years.

## Known quirks, not corrected

These are listed in `data/state/MANIFEST.json`. The archive alone isn't enough
to correct them.

- **16 retention rows** have `pct_yes` ≠ yes/(yes+no) by more than 0.001.
  Eight of them are Maryland 1998–2006. The worst is Oklahoma 2002 (Lavender):
  `no` = 27,467 against `pct_yes` 0.6798, which fits about 274,600 votes, so a
  digit was probably dropped. Prefer the counts when they disagree, and use
  `pct_yes` for Lavender.
- **23 Election rows** have no Seats row with the same seatid and year. Most are
  off by a year or two (often a primary dated differently from its general);
  a few are a decade or more apart (Alabama 2014 vs 1988, Texas 1990 vs 2000).
  Join Elections to Seats on `seatid` and check the year rather than assuming
  it.
- **Candidate names are free text** and inconsistent ("Jim Rice" / "James A.
  Rice", "Calister" / "Callister", "Bill Dalton" for D'Alton). There is **no
  person identifier**, so following one justice across elections requires
  matching names. `find_state_judge()` matches all the words of a query, in
  any order.
- The codebook says coverage ends in 2020, but the data include 2022 (50
  election, 43 seat and 38 retention rows) and a few 2021 and 2023 elections.
  The 2022 correlations use only the preceding governor's race.
- `numcandidates` counts Nevada's "none of the above" and a few write-ins, so
  it can exceed the number of named candidates (29 rows).
- Seats has five 1945 rows (Illinois, Kentucky, Michigan off-year elections).
- Seats `incumbent` has one undocumented value, `EW/AL`.

## Selection-method spans (derived)

`selection.csv` is **not part of the archive**. It infers each state's
selection system from the elections that actually took place. Each row gives
`state`, `court` (`sc`, or `cr` for the Texas and Oklahoma Courts of Criminal
Appeals), `method` (partisan / hybrid / nonpartisan / retention), `start`,
`end`, and the evidence behind them: `first_obs`, `last_obs` and `n_obs`.

How the spans are built:

- **Two layers.** The ballot format of seats up for election (Seats
  `BallotFormat`) and retention votes (types 20 and 21) are tracked separately,
  so a state can be in both: Illinois, Pennsylvania and New Mexico elect
  justices on a partisan ballot and later hold retention votes on them. Montana
  and Utah's reverted elections count as nonpartisan, which is legally what they
  were.
- **Splitting.** A method's observed years are split where none occurred for
  more than 12 years *and* another method appeared in between. North Carolina,
  for example, becomes partisan → nonpartisan (2004–2017) → partisan (2018–).
- **End year.** A span runs until the year before the next different method's
  first election, so a switch year counts as the old method until the first
  election under the new one. A final span runs to 2023 if the method was used
  within 12 years of that; otherwise it ends at its last election (New York,
  1974).
- **Start year.** A state's first span is backdated to 1946 if its first
  observed election was 1946–1955. Otherwise it starts at the first
  observation, so Alaska's starts in 1962, not at statehood in 1959.

The transitions match the known histories: Arizona hybrid → retention 1974/76;
Utah partisan → nonpartisan 1951, then retention from the late 1980s; Georgia
partisan → nonpartisan 1983/84; Kentucky 1975/76; Mississippi 1994; Tennessee
partisan → retention 1994; Arkansas 2002; West Virginia 2016; Ohio hybrid →
partisan 2022; and the merit-plan adoptions in Kansas (1958), Iowa (1962),
Colorado (1966), Oklahoma (1967), Indiana (1970), Wyoming (1972) and Florida
(1976). **The exact switch year is approximate.** It is the first election held
under the new method, not the date the law changed, and it is less reliable
than the method itself. Check the state's own history before an analysis turns
on a particular year.

`state_selection(state, year)` returns a list of methods for that year. It
returns `[]` when the state did not elect justices that year (states outside the
archive, and New York after 1974), and `None` when the archive cannot say
(before 1946, or before a state's first observed election). Spans that end in
2023 are treated as still in force.

## Linking to the SCDB

The SCDB codes every state high court as **`caseSource` = 300** ("State Supreme
Court"), with the state in **`caseSourceState`**. `states.csv` maps those codes
to postal codes, and `add_state_selection()` attaches the selection method in
the case's `term`:

```python
c  = scdb.add_state_selection(scdb.formally_decided(scdb.load("case")))
st = c[c.caseSource == 300]          # + source_state, state_selection
st.groupby("state_selection").size()
```

There are 4,883 formally decided cases from state supreme courts. From 1946 on,
all but 17 get a method: 12 come from the D.C. Court of Appeals and 3 from
Puerto Rico, which are not states, and 2 are Alaska cases from 1961, before its
first observed retention vote. Before 1946 almost everything is `<NA>`, since
only California and Missouri retention go back that far. Points to keep in mind:

- **`state_selection` describes how the court's justices were chosen, not the
  particular justices who decided the case.** Justices who were appointed to
  fill a vacancy and have not yet faced voters sit on elected courts too. For
  justice-level questions, use the elections and their dates.
- `caseSource` 300 does not distinguish Texas's and Oklahoma's two high courts.
  Their methods agree in every year, so the supreme court's is used.
- `sources=(300, 301, 302)` extends the attachment to cases from state
  intermediate and trial courts. The method is still the state *supreme* court's,
  which may not be how the lower court was chosen.
- To compare elected and appointed courts, `"none"` is the appointed group, but
  it combines gubernatorial appointment, legislative election (South Carolina,
  Virginia) and commission systems with reappointment. The archive does not
  distinguish them.

## Not bundled: county returns and the state workbooks

`state-elections-raw/AllFiles.7z` also holds the 38 state workbooks: 1,389
sheets of county-level returns (for the judicial races and the governor's races
behind the correlations), lists of justices, district definitions, turnout, and
Kritzer's source notes. Their layouts differ from state to state, and the Seats
table is the merge of their "summary" sheets, so they are not loaded. To read
one:

```python
import sys, io, pandas as pd; sys.path.insert(0, "SKILL_DIR/scripts"); import un7z
wb = un7z.read("state-elections-raw/AllFiles.7z")["WI Judicial.xlsx"]
pd.ExcelFile(io.BytesIO(wb)).sheet_names
```

Wisconsin (from 1852) and Minnesota (from 1857) have pre-1946 summary sheets.
These are the only source for those years.

## Rebuilding

```bash
python scripts/build_state_elections.py --raw ../state-elections-raw --out data/state
```

The build writes deterministic gzip with mtime 0, so an unchanged source
rebuilds byte-identically, and it regenerates `references/state_value_labels.csv`.
When Kritzer posts an update:

1. Drop the new `.7z` files into `state-elections-raw/` and rebuild.
2. Any fix whose problem the update has corrected stops the build with "found X,
   expected Y". Delete that fix from `FIXES` in the script and rebuild.
3. If the update adds years, raise `DATA_END`.

## Citing

Cite the archive and the book (`python scripts/scdb.py cite`). Say that the
selection spans and the corrections are derived in this repository and are not
part of the archive. The Arizona 2022 counts come from Ballotpedia.
