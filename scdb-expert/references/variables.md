# SCDB variable guide (all 61 variables)

Concise, analysis-oriented summary of every column in the combined files. For the
codebook's own wording read `codebook_text.md` (section numbers given as §N); for
code→label mappings use `value_labels.csv` (or `scdb.labels("<var>")`).

**This file covers the Supreme Court variables only.** The Judicial Common Space
columns are documented in `jcs.md`; the 74 courts-of-appeals columns in
`coa.md`, with their codes in `coa_value_labels.csv` (or `scdb.coa_labels("<var>")`).
Several CCAD columns share SCDB names but not SCDB codes — the disposition and
direction scales especially — so read `coa.md` before carrying anything across.

"Blank %" = share of rows with no value, Legacy (1791–1945) / Modern (1946–2025),
case-centered file. High missingness is usually structural (the attribute does not
apply), not a data error — the notes say which.

## Contents
1. Identification (§3–11)
2. Background: parties, jurisdiction, lower courts (§12–28)
3. Chronological (§29–34)
4. Substantive: issue, direction, law (§35–43)
5. Outcome (§44–49)
6. Case-level voting (§50–55)
7. Justice-level variables (§56–63, justice file only)
8. Quick map: question → variable

---

## 1. Identification

| variable | what it is | blank % | notes |
|---|---|---|---|
| caseId | `TTTT-NNN` term + sequence | 0/0 | Primary key of the case file; sorts chronologically within term. |
| docketId | caseId + `-DD` docket | 0/0 | Always `-01` in citation-organized data (lead docket only). |
| caseIssuesId | docketId + `-II` issue/provision | 0/0 | Always `-01` here (first issue only). |
| voteId | caseIssuesId + `-SS-VV` split vote + justice seq | 0/0 | Unique per justice row in justice file; in case file ends `-01-01`. |
| usCite | U.S. Reports cite | 0/5.7 | Blank for recent cases not yet paginated (roughly 30–75 per term from OT2016 on). Not unique (several cases can share a page). |
| sctCite | Supreme Court Reporter | 31.4/0.1 | S. Ct. starts 1882, hence legacy blanks. |
| ledCite | Lawyers' Edition | 0.1/0.1 | Best universal fallback cite. |
| lexisCite | LEXIS cite | 0/0 | **Unique** — safest cite key for merging with other datasets. |
| docket | Court docket number | 24.6/0.1 | Legacy reports often lack one. Pre-1971 numbers repeat across terms, so docket alone is not a key; use (term, docket). |

## 2. Background

| variable | codes | blank % | notes |
|---|---|---|---|
| caseName | text | 0/0 | Upper case. Modern names use curly quotes (’). Legacy names from L. Ed.; variant spellings common — search by cite if a name fails. |
| petitioner / respondent | varParties (311) | 0/0 | Party *as characterized in the opinion* (e.g. "employer" vs "business"). Very granular; researchers usually collapse (e.g. federal gov't, state gov't, business, individual). |
| petitionerState / respondentState | varStates (64) | ~80–90% | Only when the party is a state or state/local entity; blank otherwise. |
| jurisdiction | varJurisdiction | 0/0 | 1 cert, 2 appeal, 9 original, 13 writ of error (dominant in legacy era). |
| adminAction | varAdminAction (125) | 76/73 | Agency whose action preceded litigation (blank if none) — useful for administrative-law work. |
| adminActionState | varStates | ~92 | State agency's state. |
| threeJudgeFdc | 0/1 | ~0 | Three-judge district court below. |
| caseOrigin / caseSource | varCaseSources (211) | ~2–4 | Origin = trial court; source = court whose decision SCOTUS reviewed. Codes 154,156,157,158,161 appear in 7 modern cases but are undocumented. |
| caseOriginState / caseSourceState | varStates | ~75 | For state courts and single-state federal districts. |
| lcDisagreement | 0/1 | ~0 | Dissent noted in the court below. |
| certReason | varCertReason (13) | 0/1.0 | 1 = did not arise on cert (most legacy cases). |
| lcDisposition | varCaseDispositionLc (12) | 58.4/13.6 | Blank when SCOTUS reviewed a trial court or original jurisdiction — very common in legacy era. |
| lcDispositionDirection | varDecisionDirection | 4.8/2.3 | Largely *derived* from decisionDirection + caseDisposition (see §28 rules), so not independent evidence of lower-court ideology. |

## 3. Chronological

| variable | notes |
|---|---|
| dateDecision | m/d/yyyy in the files (parsed to datetime by `scdb.load`). Only reliable chronological ordering; page numbers are not chronological. |
| term | Term of decision; reargued cases take the later term. Term start dates changed over history (§30). **Two 1850 terms** share the value 1850 (January and December). |
| naturalCourt | varNaturalCourt: chief-justice code ×100 + sequence (1710 = Roberts 10). Strong natural courts, but coded per case — some legacy codes span personnel changes and some modern cases carry the earlier court's code (e.g. Gundy, 2019, coded 1706). See `natural_courts.csv` for observed date ranges and participants. |
| chief | **Text** (surname) in the data, not a code. |
| dateArgument | First day of argument. Blank = not argued *or* date unknown (24% legacy). |
| dateRearg | Reargument date; ~98% blank. |

## 4. Substantive

| variable | codes | blank % | notes |
|---|---|---|---|
| issue | varIssues (278) | 0.3/0.7 | Subject matter from a public-policy standpoint. Leading digits of the 5–6 digit code = issueArea (10010 → 1, 140010 → 14; exception: 110033, incorporation of foreign territories, is filed under issueArea 13 Miscellaneous). **Legacy: first issue only.** |
| issueArea | varIssuesAreas (14) | 0.3/0.7 | 1 Criminal Procedure … 8 Economic Activity, 9 Judicial Power, 10 Federalism, 12 Federal Taxation, 14 Private Action (common-law; almost entirely legacy — 3,328 legacy vs 7 modern). |
| decisionDirection | 1 cons, 2 lib, 3 unspecifiable | 0.3/0.5 | Defined relative to *issue*; rules in §37. Unspecifiable is 18% of legacy cases vs <2% modern (private law, interstate relations). See analysis_guide.md for critiques. |
| decisionDirectionDissent | 0 opposite, 1 same direction | 0.3/3.7 | 1 = majority and dissent both lean the same way (rare). The codebook narrative's example uses 0/1 for cons/lib — ignore it; the value labels are authoritative. |
| authorityDecision1/2 | varAuthorityDecision (7) | 0.3/~85 (2nd) | Basis: judicial review (national/state), supervision, statutory construction, admin regulation, diversity, federal common law. |
| lawType | varLawArea (8) | 0.4/13.5 | Constitution, amendment, federal statute, court rules, other, infrequent statutes, state/local law, **9 = no legal provision (54% of legacy cases)**. |
| lawSupp | varLegalProvisions (206) | 0.4/13.5 | Specific provision (e.g. 210 = Fifth Amendment self-incrimination). Legacy coverage very incomplete. |
| lawMinor | free text | 82/70 | Statute cites for infrequently litigated laws ("28 U.S.C. § 1291"). Messy: contains stray values like "NA" or dates. |

## 5. Outcome

| variable | codes | notes |
|---|---|---|
| decisionType | varDecisionTypes | 1 signed opinion; 2 per curiam, not argued; 4 decree; 5 equally divided; 6 per curiam, argued; 7 judgment of the Court (plurality); 8 seriatim (1792–1847 only). No code 3. Choice of types defines the sample — see analysis_guide.md. |
| declarationUncon | 1 none, 2 federal, 3 state/territorial, 4 local | Coded per citation; one cite can strike several laws, so counts ≠ number of laws struck. |
| caseDisposition | varCaseDispositionSc (11) | What SCOTUS did to the court below. **Governs who counts as majority vs dissent in the justice file.** Mostly blank for original jurisdiction. |
| caseDispositionUnusual | 0/1 | 1 = disposition did not fit the scheme; caseDisposition holds the closest code. |
| partyWinning | 0 lost, 1 won (fully or partly), 2 unclear | Derived mainly from caseDisposition (affirm/dismiss → 0; reverse/vacate → 1). A vacatur counts as a win. |
| precedentAlteration | 0/1 | Majority (occasionally a clear dissent or later Court) says a precedent is overruled/disapproved. "Distinguishing" doesn't count. One flag per citation regardless of how many precedents fell. |

## 6. Case-level voting

| variable | notes |
|---|---|
| voteUnclear | 1 = a concur-in-part/dissent-in-part vote could be read either way. |
| majOpinWriter | varJustices. Blank for per curiams (18.9% modern). For decisionType 7 it is the plurality author. |
| majOpinAssigner | Inferred from final-vote coalition + seniority rules, **not** from conference records; wrong in ~16% of cases per the codebook. |
| splitVote | Always 1 in these citation files. |
| majVotes / minVotes | Justices agreeing / disagreeing with the *disposition*, not with any particular issue. Equally divided cases read 4–4 (or 3–3), but every justice row shows vote = 8 with majority blank. |

## 7. Justice-level variables (justice file only)

Each case has one row per sitting justice, **including non-participants** (vote blank).
10-member rows occur in the 1863–1864 terms.

| variable | codes | notes |
|---|---|---|
| justice | varJustices (118) | Unique person id (1 = Jay … 118 = Jackson). Rutledge has two ids (2 and 9) for his two stints; Harlan I = 45, Harlan II = 91. Renumbered in SCDB_2012_01 — old datasets use different ids. Same ids used by Martin–Quinn scores. |
| justiceName | text | Short name, e.g. `AScalia`, `JHarlan2`. |
| vote | varVote (8) | 1 with majority; 2 dissent; 3 regular concurrence; 4 special concurrence (judgment only); 5 judgment of the Court; 6 dissent from cert denial/summary affirmance; 7 jurisdictional dissent; 8 equally divided; blank = did not participate. |
| opinion | 1 none, 2 wrote, 3 co-authored | Blank for non-participants. |
| direction | 1 cons, 2 lib | Blank if non-participant **or** case direction unspecifiable (22% legacy). |
| majority | 1 dissent, 2 majority | Blank for non-participants and vote = 8. Note vote = 7 (jurisdictional dissent) is coded majority = 1 even though the codebook calls it nonparticipation; vote = 6 rows also carry majority = 1. |
| firstAgreement / secondAgreement | varJustices | Author(s) of separate opinions this justice joined. Value 0 appears ~2,700 times (undocumented; treat as "none"). The majority opinion is not recorded as a "join". |

## 8. Quick map: question → variable

- *Was it argued?* dateArgument (non-blank) or decisionType ∈ {1, 6, 7}.
- *Who won?* partyWinning (petitioner's perspective) + caseDisposition.
- *Liberal/conservative outcome?* decisionDirection (case) / direction (justice).
- *How close?* majVotes, minVotes; unanimity = minVotes == 0.
- *Struck down a law?* declarationUncon ∈ {2, 3, 4}.
- *Overruled precedent?* precedentAlteration == 1.
- *Which court below?* caseSource (+ caseSourceState); circuit reversal rates → caseSource + caseDisposition.
- *Agency cases?* adminAction non-blank; petitioner/respondent codes for federal agencies.
- *Subject?* issueArea → issue → lawType/lawSupp/lawMinor, in increasing specificity.
- *Who wrote/joined what?* majOpinWriter; opinion; firstAgreement/secondAgreement.

Courts of appeals equivalents (see `coa.md`; CCAD codes differ from SCDB's):

- *How many cases from a circuit?* circuit + year.
- *Who wrote it?* author_id / author_name (`author` alone is a panel-slot index).
- *Who else was on the panel?* j1_id–j3_id, j1_name–j3_name; enbanc_id for en banc.
- *Panel composition?* num_dems, num_women, num_nonwhite, mixed_panel.
- *Panel or judge ideology?* author_ghp, ghp_med (and ghp_min/max/mean); compare
  with the circuit via `add_coa_circuit_medians()`.
- *Outcome below?* scdb_first_disposition — remap with `coa_disposition_to_scdb()`.
- *Liberal/conservative?* scdb_second_direction_mech, already in SCDB coding.
- *Did the Supreme Court review it?* `add_scdb()`; songer_gt_supct is a
  recall-only flag, not a reliable negative.
