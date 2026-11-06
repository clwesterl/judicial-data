# Analysis guide: doing SCDB work correctly

Read the section(s) relevant to the task. The goal is analyses a judicial-politics
referee would accept: explicit sample definitions, defensible codings, and honest
caveats.

## Contents
1. Define the sample first
2. Legacy vs Modern comparability
3. The direction (liberal/conservative) variables
4. Justice-level vote analysis
5. Counting common quantities correctly
6. Measurement models (IRT / ideal points)
7. Merging with other data
8. Courts of appeals work
9. Reporting checklist

---

## 1. Define the sample first

Nearly every disagreement about SCDB numbers traces back to the sample. State it.

**Unit.** These files are organized *by citation*: one row per case (lead docket,
first issue/legal provision). Consolidated dockets and additional issues are
invisible. That is right for "how many cases / how did the Court rule" questions;
it is wrong for docket-level dispositions (consolidated cases can be disposed of
differently) or multi-issue analyses. If a task needs those, say that the
docket- or issue/legal-provision-organized SCDB files are required (Modern era
only; Legacy has citation-level only).

**decisionType filter.** Common conventions:
- *Orally argued, formally decided cases* (the default for most studies):
  `decisionType in {1, 6, 7}`. Add 5 (equally divided) when counting the Court's
  argued docket; exclude 5 for anything about direction or votes (no majority).
- Add 2 (unargued per curiams) only when summary reversals etc. are the point.
  The database does **not** contain all unargued per curiams or memorandum
  decisions, so type 2 is a partial census.
- 4 (decrees) are mostly original-jurisdiction boundary cases; usually drop.
- 8 (seriatim) exists only 1792–1847.
- Legacy caveat: type 1 no longer requires a known argument date (dates are
  missing for many argued cases). For "known to be argued," require non-blank
  `dateArgument` and accept that you lose some argued cases.

**Time unit.** Use `term` (OT2025 = October 2025–summer 2026), not calendar year of
`dateDecision`, unless the question is explicitly about calendar time. Term start
rules changed over history, and the value 1850 covers two terms (January and
December 1850).

**Natural courts.** `naturalCourt` is coded per case and is not always a clean
"no personnel change" window (legacy codes such as 601 Chase 1 and 701 Waite 1
span several changes; some modern cases keep the earlier court's code, e.g.
Gundy, 2019 → 1706). If membership matters, define windows from the justice file
(who actually participated) — `references/natural_courts.csv` lists observed
participants and date ranges per code.

## 2. Legacy vs Modern comparability

Treat 1945/1946 as a seam, not a continuous series.

- **Coding process.** Modern cases (1953+, Vinson back-coded) were coded close to
  decision; Legacy cases were coded retrospectively onto a 20th-century issue
  scheme ("definitional stretching" by the codebook's own admission).
- **First issue only.** Legacy records carry only the first issue and legal
  provision, so issue- and provision-specific counts are undercounts.
- **Legal provisions sparse.** `lawType == 9` (no legal provision) for 54% of
  Legacy cases; `lawSupp` coverage is thin before the Civil War.
- **Case mix.** Pre-1925 (Judges' Bill) the docket was largely mandatory: writs of
  error and appeals, heavy private-law content (issueArea 14 "Private Action" is
  ~17% of Legacy cases, ~0 Modern). Mandatory appellate jurisdiction mostly ended
  in 1988. Shifts in rates (reversal, unanimity, direction) partly reflect
  docket control, not behavior.
- **Direction unspecifiable** in 18% of Legacy cases vs <2% Modern; direction
  shares computed over "specifiable" cases have shifting denominators.
- **Votes.** Early reporters often did not record absences; Marshall-era opinions
  sometimes note unnamed dissenters (`voteUnclear`). Legacy dissent rates are
  low partly by norm (the "norm of consensus"), partly by recording.

For long time series, show Legacy and Modern separately or include an era
indicator, and run a sensitivity check that starts in 1946 (or 1925).

## 3. The direction variables

`decisionDirection` codes the outcome relative to the **issue** (§37 of the
codebook has the full rules). Key conventions that surprise people:
- Economic activity/unions: liberal = pro-government, anti-business,
  pro-competition, pro-union (except union antitrust), pro-injured person.
- Judicial power: liberal = pro-exercise of judicial power / pro-judicial review.
- Federalism: liberal = pro-federal power, anti-state.
- Federal taxation: liberal = pro-United States.
- Takings: pro-government/anti-owner = liberal (with exceptions).
- Interstate relations and private law: unspecifiable (3).
- Liability issues depend on who is the injured party (§37).

Known critiques to mention when direction drives a result:
- Harvey & Woodruff (2013, *Journal of Law, Economics & Organization*) report
  evidence consistent with confirmation bias in direction coding (coder knowledge
  of the justices affecting codes).
- Shapiro (2009, *Hastings Law Journal*) questions the reliability of issue and
  direction coding for legally complex cases.
- Direction is a single dimension; for issue areas like federalism, judicial
  power, and economic activity the mapping to ideology is contestable.

Robustness moves: restrict to issue areas with uncontroversial direction (e.g.
criminal procedure, civil rights, First Amendment); report results with and
without federalism/judicial power; or use the direction-free outcome
(`partyWinning`, reversal) where substantively appropriate.

`lcDispositionDirection` is largely derived from `decisionDirection` and the
disposition (§28), so do not treat it as an independent measure of lower-court
ideology when modeling the Court's direction (it is mechanically related).

## 4. Justice-level vote analysis

The justice file has one row per sitting justice per case, **including
non-participants**. Build analysis sets explicitly:

```python
v = scdb.load("justice")                    # placeholders dropped
part = v[v.vote.notna()]                    # participated in some form
merits = part[part.vote.isin([1, 2, 3, 4, 5])]   # merits votes only
```

- `vote` 6 (dissent from cert denial / summary affirmance) and 7 (jurisdictional
  dissent) are nonparticipation on the merits per the codebook, yet carry
  `majority == 1`. Excluding vote ∈ {6, 7, 8} is the usual choice; say so.
- `majority`: 2 = with the disposition, 1 = dissent. Concurrences in the judgment
  (vote 4) are majority votes.
- `direction` is blank when the case is unspecifiable — that is not
  non-participation.
- Majority-opinion membership (joined the opinion, not just the judgment):
  vote ∈ {1, 3} plus the author (and vote 5 authors of judgments of the Court).
  Vote 4 = judgment only.
- Separate-opinion joins: `firstAgreement`, `secondAgreement` hold the author id(s)
  of separate opinions joined; 0 means none (undocumented value).

**Pairwise agreement** (e.g. Thomas–Alito): restrict to cases where both cast merits
votes; agreement = same `majority` value. Report the denominator. For "opinion
agreement" (the Harvard Law Review style), agreement means joining the same opinion
— reconstruct from vote ∈ {1,3} (majority opinion) and the join variables.

**Swing / median.** Share of time in the majority in 5–4 cases
(`majVotes == 5 & minVotes == 4`); with vacancies, 5–3 and 4–4 cases change the
arithmetic, so condition on the number of participants.

**Opinion assignment.** `majOpinAssigner` is inferred from the final vote and
seniority, not from conference records; the codebook estimates it is wrong for
~16% of cases. Don't build assignment models on it without that caveat.

## 5. Counting common quantities

- **Cases per term:** count rows of the case file after the decisionType filter.
  Citation-level counts are lower than docket counts.
- **Unanimity:** `minVotes == 0` among formally decided cases; exclude
  decisionType 5. Note unanimity on the judgment ≠ unanimity on the opinion
  (special concurrences).
- **Reversal rate:** `caseDisposition in {3,4,5,6,7,8}` (partly or fully
  reversing/vacating) or `partyWinning == 1`; they nearly coincide by construction.
  Rates by circuit: group by `caseSource` (federal courts of appeals codes).
- **Laws struck down:** `declarationUncon in {2,3,4}` counts *citations*, not
  laws; one case can strike several provisions. Cross-check with CONAN.
- **Overrulings:** `precedentAlteration == 1` counts overruling *cases*; the
  number of precedents overruled needs reading the opinions.
- **Majority opinion counts per justice:** `majOpinWriter` in the case file;
  per curiams have no writer; decisionType 7 writers are plurality authors.
  `references/justices.csv` has precomputed totals.

## 6. Measurement models (IRT / ideal points)

For ideal-point work, the standard input is a justice × case matrix of binary
votes on non-unanimous, orally argued cases, typically coded by direction
(liberal = 1) or by majority/dissent with a case-specific polarity.

```python
v = scdb.load("justice"); c = scdb.load("case")
keep = c[(c.decisionType.isin([1, 6, 7])) & (c.minVotes > 0)].caseId
y = v[v.caseId.isin(keep) & v.vote.isin([1, 2, 3, 4, 5]) & v.direction.notna()]
y = y.assign(lib=(y.direction == 2).astype(int))[["caseId", "term", "justice", "lib"]]
# long format → Stan: integer-index justices and cases, pass N, J, K, jj, kk, y
```

Identification in a 2PL model: fix the sign (e.g. constrain a known liberal and a
known conservative justice, or a positive discrimination prior on cases coded by
direction) and the scale (standard-normal prior on ideal points). Dynamic models
(Martin–Quinn style) add a random walk over terms. If you use `direction` as the
outcome, you inherit the direction-coding critiques in §3; coding by
majority/dissent with estimated case polarity avoids that dependence.

Judicial Common Space scores for justices (Martin–Quinn mapped into the Common
Space, OT1937–OT2022) are bundled: `scdb.add_jcs(votes)`. See references/jcs.md,
including the circularity caveat when the same votes are both outcome and input.
Raw Martin–Quinn scores are not bundled; their justice file uses SCDB-style
identifiers, but verify the join on a few names.

## 7. Merging with other data

- **Keys:** `lexisCite` is unique and present for every case — best cite key.
  `usCite` is not unique and is blank for many recent cases; normalize spacing and
  periods before matching (`scdb.find` does this).
- **CourtListener** stores SCDB caseIds for its Supreme Court opinions — merge on
  `caseId` to get opinion text.
- **Justices:** merge on `justice` (numeric id) — ids were renumbered in
  SCDB_2012_01, so older derived datasets may be off.
- **Lower courts:** `caseSource`/`caseOrigin` codes identify circuits and state
  courts. For circuit-level work the Comprehensive Court of Appeals Database is
  bundled here — `add_coa()` attaches the reviewed CoA case directly. Note this is
  a **derived fuzzy match**, not an official linkage; see §8 and references/coa.md.
- **Agencies:** `adminAction` (125 agency codes) plus federal-agency party codes.
- **Ideology:** Judicial Common Space tables join by justice + term, by term (Court,
  House, Senate, president medians), and by `caseSource` (circuit medians) — see
  references/jcs.md.

## 8. Courts of appeals work

Read references/coa.md before doing any of this — it carries the code-scheme
corrections and the validation figures. The essentials for analysis:

**Sample definition.** The CCAD universe is *published* opinions, 512,263 of them,
1880–2025. That is not the universe of appellate decisions: unpublished
dispositions are excluded, and their share has grown enormously, so a series that
runs to the present is measuring a shifting slice of the docket. Say so. The
recommended clean-panel filter is

```python
p = d[(d.judge_count == 3) & (d.all_judges_matched == 1) & (d.all_authors_matched == 1)]
```

`judge_count == 3` already excludes en banc, so a separate `is_enbanc == 0` is
redundant. One row is one published opinion-bearing case, so rehearings appear as
separate rows for the same litigation.

For **author-level** work add `is_percuriam != 1` rather than relying on
`all_authors_matched`. 16.1% of cases are per curiam and carry no author; excluding
them makes `author_id` and `author_name` complete, whereas
`all_authors_matched == 1` drops only 0.9% and still leaves 18.6% of authors
unnamed. `author_ghp` is missing for a further 3.1% (no GHP score).

**Direction.** The weakest of the LLM-coded variables. Prefer
`scdb_second_direction_mech` over `scdb_first_direction_oneshot` (82.1% vs 80.4%
against Songer hand coding per the codebook). Conditional on both sources calling a
case conservative-or-liberal, the mechanical variable agrees with Songer 78.2% of
the time (n = 12,186) — fine for aggregates, shaky case by case. Drop code 3
(unspecifiable) rather than treating it as a middle category; it is assigned by
issue-area rule, covering 100% of Private Action and Interstate Relations. All the
§3 critiques of SCDB direction coding apply here too, with LLM coding error on top.

**Ideology.** `author_ghp` and the `ghp_*` panel aggregates are
Giles–Hettinger–Peppers scores, the same measure behind the JCS appeals-judge
scores, so judges, panels and circuits share one scale.
`add_coa_circuit_medians()` attaches the deciding circuit's JCS median for the year,
making `ghp_med - circuit_median` a panel's distance from its circuit. GHP is
**appointment-based and fixed**, so it carries no within-judge variation over time —
it cannot speak to whether a judge drifted, and individual-level direction
relationships are correspondingly weak (mean `author_ghp` is 0.081 for
conservative-coded decisions and 0.032 for liberal ones). The panel aggregates are
the sturdier choice for inference.

**Panel effects** replicate cleanly, which is a useful check that a merge is right.
On 380,085 clean three-judge panels, the share coded liberal rises monotonically
with Democratic appointees — 34.5 / 37.6 / 41.7 / 44.7% for 0/1/2/3, and more
steeply from 1980 on (32.1 / 36.5 / 43.4 / 49.8%). If your filter does not
reproduce something close to this, suspect the direction coding first.

**Linking to the Supreme Court.** `add_coa()` and `add_scdb()` join through the
derived crosswalk. Report the tier (A is ~0.9% false positives, covering 68% of
SCDB circuit-origin cases) and describe it as a fuzzy match. Two biases to state:
recall is capped near 75% for structural reasons — consolidation, officeholder
substitution, dispositions that never became an SCDB case — and linkage is weakest
in recent terms (53% in the 2020s) because of the published-opinion limitation. Both
are plausibly correlated with case type, so do not treat the linked set as a random
sample of reviewed cases. Selection runs the other way too: cases the Court reviews
are not a random sample of circuit decisions, which is the whole point of most
designs here but needs modelling rather than assuming.

## 9. Reporting checklist

State in any write-up: SCDB release(s) used (`python scripts/scdb.py cite`);
citation-organized data; the decisionType filter; the time unit (term); how
non-participation, equally divided cases, and unspecifiable direction were
handled; whether Legacy and Modern eras were pooled. For courts of appeals work,
add: that the CCAD covers published opinions only; which direction variable and how
code 3 was handled; the clean-panel filter; and for anything linked to the SCDB, the
crosswalk tier plus the recall and false-positive figures.
