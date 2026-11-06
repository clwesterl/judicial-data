# Judicial Common Space (JCS)

The JCS places Supreme Court justices, federal courts of appeals judges, members
of Congress, and presidents on one ideological scale: the DW-NOMINATE Common Space
metric, roughly −1 (liberal) to +1 (conservative). It is what makes "is the Court
median to the right of the Senate median?" or "how far is the Ninth Circuit from the
Court?" answerable on a single scale.

Cite: Epstein, Martin, Segal & Westerland (2007), *JLEO* 23(2): 303–325. Also cite
the component measures when they matter: Martin & Quinn (2002), *Political Analysis*
10(2): 134–153 (justices); Giles, Hettinger & Peppers (2001), *Political Research
Quarterly* 54(3): 623–641 (lower-court judges). `python scripts/scdb.py cite` prints
the JCS citation with the SCDB ones.

## Contents
1. What is in each table
2. Linking to the SCDB
3. Measurement caveats
4. Data quirks
5. Typical uses

---

## 1. Tables (`data/jcs/`, built by `scripts/build_jcs.py` from `jcs-raw/`)

| table (`scdb.jcs(...)`) | rows | columns | notes |
|---|---|---|---|
| `"justice"` → jcs_justice_term.csv | 782 justice-terms, 49 justices, OT1937–OT2022 | term, justice (SCDB id), justiceName, jcs | Time-varying, behavior-based: Martin–Quinn scores mapped into the Common Space (transformation in Epstein et al. 2007). Terms with 10–11 justices reflect mid-term personnel changes. |
| `"coa"` → jcs_coa_judges.csv | 705 judge-circuit rows, 693 judges | judge_key, name, last_name, first_middle, suffix, circuit, circuit_name, scdb_caseSource, scdb_justice, jcs | One fixed score per judge, appointment-based (Giles–Hettinger–Peppers: the home-state senators' Common Space scores when senatorial courtesy applies, otherwise the appointing president's). |
| `"medians"` → jcs_medians.csv | 102 rows, calendar years 1924–2024 | year, term, congress, president, house_median, senate_median, sc_median, circuit_median1–13, circuit_sd1–13 | `term = year − 1` (verified): the row for year Y describes the Court term decided mostly in Y. `sc_median` equals the median justice score in that term (verified for all 86 terms). |
| `"circuit_medians"` | long reshape of the above | year, term, circuit, circuit_name, scdb_caseSource, median, sd | Convenience view; drops missing medians. |
| `"circuits"` → circuits.csv | 13 | circuit, circuit_name, scdb_caseSource, first_year_with_median | JCS circuit 1–11 = regional circuits, 12 = D.C., 13 = Federal. |

Values are rounded to 6 decimals; the raw files stored single-precision floats
(0.395999997854233 = 0.396), so nothing substantive is lost.

## 2. Linking to the SCDB

| link | key | helper |
|---|---|---|
| Justice score onto votes | SCDB `justice` + `term` (all 49 JCS justices matched SCDB `justiceName`) | `scdb.add_jcs(votes)` / `scdb_add_jcs()` |
| Court, House, Senate, president medians onto cases | SCDB `term` = medians `term` | `scdb.add_medians(df, cols=...)` / `scdb_add_medians()` |
| Median of the circuit whose decision the Court reviewed | SCDB `caseSource` ↔ `scdb_caseSource`, calendar year = term + 1 + `year_offset` | `scdb.add_circuit_medians(cases, year_offset=0)` |

SCDB caseSource codes: 21–31 = First–Eleventh Circuits, 32 = D.C. Circuit, 8 = Federal
Circuit. Pre-1891 circuit courts and other federal courts get no circuit median.
The lower-court decision usually predates the Supreme Court term by 1–2 years, so
report results with `year_offset` of 0, −1, and −2.

**Courts of appeals judges → other data.** The file has names only (no FJC judge
id), so linking to case-level appeals data means name matching on `judge_key`
(ASCII-folded, lowercased, punctuation → `_`) plus circuit. Check common surnames by
hand. The twelve judges moved from the Fifth to the Eleventh Circuit in 1981 appear
once per circuit with the same score. The 21 judges later elevated to the Supreme Court carry
`scdb_justice` (hand-verified crosswalk in build_jcs.py; name matching alone would
wrongly pair Thomas A. Clark with Tom C. Clark and Shackelford Miller with Samuel F.
Miller). They have both an appointment-based CoA score and behavior-based justice
scores — different measures, not a time series.

## 3. Measurement caveats

- **Different measurement models by institution.** Justices' scores come from their
  votes and move over time; appeals judges' scores are fixed at appointment and
  cannot show drift. Cross-institution comparisons rest on the Common Space mapping.
- **Circularity.** Justice scores are estimated from the same non-unanimous votes the
  SCDB records. Using JCS (or MQ) to "explain" SCDB votes or decision direction in the
  estimation period is partly circular; lag the scores, use out-of-sample terms, or
  model votes and ideal points jointly.
- **Point estimates only.** The files carry no posterior uncertainty; for Bayesian
  work treat the scores as noisy (or re-estimate MQ from the SCDB votes, see
  analysis_guide.md §6).
- **Direction scale ≠ SCDB direction coding.** A conservative JCS score and a
  "conservative" SCDB `decisionDirection` are measured differently; their
  correspondence is an empirical question.

## 4. Data quirks

- **Coverage gaps.** Justice scores stop at OT2022 (the medians table runs to year
  2024 / term 2023 but `sc_median` is missing for term 2023), so SCDB OT2023–OT2025
  cases get no JCS values.
- **1924 appears twice** in the medians table, with president = 0.396 and 0.445 and
  otherwise identical values. Coolidge's value in 1925–28 is 0.396, so the 0.445 row
  is probably 1923 (Harding) mislabeled. Left as released; its term is missing, so
  it never enters SCDB merges.
- **President missing 1929–1932** (Hoover).
- **Fifth Circuit medians missing 1924–1964.** Two Fifth Circuit judges have no
  score (John C. Hutcheson Jr., Samuel Sibley), consistent with medians computed
  without dropping missing values. Other circuits begin in the years listed in
  circuits.csv (Eleventh 1981, Federal 1982). Fourteen circuit-year SDs are exactly 0.
- **Edges against the SCDB.** Byrnes has one SCDB vote coded term 1942 (Ex parte
  Quirin, July 31, 1942) but no 1942 JCS score. R.H. Jackson has a 1945 score though
  he sat out OT1945 (Nuremberg) and has no SCDB votes that term.
- **Name typo:** "Ginsburg, Douglas, H." (extra comma) is parsed correctly as
  Douglas H. Ginsburg.

## 5. Typical uses

- Separation-of-powers models: Court median vs. House/Senate medians and the
  president by term (`add_medians`).
- Hierarchy: distance between the Court median and the reviewed circuit's median,
  and its relation to reversal (`add_circuit_medians` + `caseDisposition`/`partyWinning`).
- Justice-level vote models with lagged ideology (`add_jcs` on the justice file,
  shifting `term` by one before merging for a lag).
