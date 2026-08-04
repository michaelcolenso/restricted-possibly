# Findings

Format: every claim states its **denominator**, its **replication count**, and what would
**falsify** it. Refutations get equal billing — they cost the same to produce and save the
next person the same detour.

Status vocabulary: **Established** (replicated, denominator, falsifier stated) ·
**Suggested** (real signal, insufficient replication) · **Refuted**.

---

## Established

### Restriction status is write-once

Restriction status does not mutate. Four independent tests on RG 263:

| Test | n | Changes |
|---|---:|---:|
| 2021→2022 snapshot diff, shared naIds | 9,985 | 0 (10 absent→Unrestricted = field backfill) |
| Oct-2018 processing batch, 2018→2025 | 33 | 0 |
| All 2021-restricted naIds, 2021→2025 | 149 | 0 |
| Exemption-code changes | 9,985 | 0 |

Breakdown of the 149: 72/72 `Restricted - Partly`, 70/70 `Restricted - Fully`,
7/7 `Restricted - Possibly` — identical across four years.

**Implication, scoped to RG 263.** Declassification does not appear as a status flip;
released material appears to arrive as *new* descriptions instead. A status-change
monitor over RG 263 would have found nothing in four years.

Do **not** read that as corpus-wide guidance. One agency's practice is not NARA's, and
whether another record group mutates status is exactly the open question — so run
`write_once_check` elsewhere before concluding a monitor is pointless there. A
counterexample would be a significant finding.

**Falsified by:** any naId whose status changes between vintages in any record group.
`inventory.write_once_check` tests this. **Replicated across: 1 agency.** This is the
weakest part of an otherwise solid result — a counterexample elsewhere would be
significant.

### In RG 263, `Other` denotes statutory exemption, not a FOIA exemption

**Scope: RG 263 only.** The evidence below is one agency's encoding convention. Whether
`Other` carries the same meaning corpus-wide is untested — §5 rule 3 requires three
record groups before generalizing, and this has one. Read it as an established fact
about RG 263 and an open question everywhere else.

RG 263 contains 27 descriptions with restriction code `Other` against 1,293 citing
FOIA (b)(1). 25 of the 27 are the CIA's Guatemala operations (naIds 5956115–5956141):
PBFORTUNE, PBSUCCESS, PBHISTORY, Lincoln Station files, cryptonyms KUHOOK / FJHOPEFUL /
Calligeris. Mostly `Top Secret`, mostly `Restricted - Fully`, no coverage dates.

The `accessRestriction.note` is identical across all 25:

> Per the Central Intelligence Agency (CIA) Information Act of 1984, these records are
> exempted from search, review, publication, or disclosure under the Freedom of
> Information Act (FOIA). They are also exempted from Mandatory Declassification Review
> (MDR) requests under Section 3.5(a)(2) of Executive Order 13526.

**Implication.** Both FOIA and MDR are foreclosed by statute. These are not obtainable
through either route; advising anyone to file on them wastes their time.

The remaining two `Other` records are not statutory exemptions at all, and only the
`note` column distinguishes them: naId 640447, the Nazi War Crimes second release,
governed by its own disclosure acts; and naId 6106938, *Records Relating to Activities
in Guatemala* — the **open** series, `Restricted - Partly` because the CIA redacted
some records before transfer. That last one is the open counterpart to the 25 above,
and is where the reconciliation problem in `OPEN-QUESTIONS.md` lives.

**Falsified by:** an `Other`-coded record elsewhere whose note cites a different basis —
which would make `Other` a general escape hatch rather than a statutory marker.
**Replicated across: 1 agency.**

### RG 263 withholding profile (survey complete)

**1,359 adjudicated withholdings of 26,858 scanned — a 5.6% rate** against a base of
1,359 restricted + 23,118 unrestricted. A further 509 records are `Restricted - Possibly`
(never reviewed) and 1,872 have no status at all; both are excluded from the rate.

| Status | n | | Exemption (adjudicated only) | n |
|---|---:|---|---|---:|
| Restricted - Partly | 1,080 | | FOIA (b)(1) National Security | 1,293 |
| Restricted - Fully | 279 | | Other | 27 |
| **Adjudicated total** | **1,359** | | FOIA (b)(3) Statute | 6 |
| Restricted - Possibly (unreviewed) | 509 | | JFK Assassination Records Collection Act | 5 |
| No status | 1,872 | | FOIA (b)(6) Personal Information | 4 |

Levels: 1,247 fileUnit, 112 series. Partial redaction outnumbers full closure nearly
4:1 — most withheld material has releasable content in it.

**Parse failures: 0.** The full pass parsed every line in all 400 shards, so these are
exact counts rather than lower bounds. `Summary.parse_failures` reports this on every
run; a non-zero value would mean each figure above understates the truth by an unknown
amount.

**Counting correction.** An earlier pass reported 1,868 restricted (~7%) by folding the
509 unreviewed records into the withheld count. `Restricted - Possibly` is a
processing-backlog marker, not a withholding decision (§4.3), so it inflated the
numerator by 37% and mixed a backlog into a secrecy statistic. The figures above are a
full re-pass with the backlog held out; `withheld_rg_263.csv` is regenerated to match
and now carries `securityClassification` and `note`.

**Denominator still matters:** a 10,000-record sample suggested ~5% restricted. That
comparison was made against the old inflated full-pass figure and no longer
demonstrates the gap it was cited for — the sampling question is open again.

### Three separable activity classes in edit timestamps (v1 only)

| Signature | Meaning | Verified instance |
|---|---|---|
| Identical stamp, `T00:00:00`, high count | Automated batch import | `2013-06-27T00:00:00` ×1,835 |
| ~45 records, real clock time, seconds apart | Human running a bulk tool | `2015-11-20T17:18:21` ×45 |
| One per 20–40s sustained for hours | Archivist working a queue | 2018-10-03 09:45→11:12, 85 records |

**Falsified by:** a midnight-clustered batch that corresponds to a documented human
process, or a steady-cadence sequence produced by a script.
**Constraint:** `recordHistory` exists only in v1 vintages (2021–2022).

---

## Suggested (insufficient replication)

### Edit intensity distinguishes adjudicated from categorical restriction

| Record group | Open | Restricted | Ratio |
|---|---:|---:|---:|
| RG 263 CIA | 1.04 | 1.52 | 1.46× |
| RG 111 Signal Corps | 2.19 | 4.08 | 1.86× |
| RG 242 Foreign Records Seized | 1.15 | 1.01 | **0.88×** |

Working interpretation: elevated per-record edit counts indicate *individually
adjudicated* restriction; flat or inverted counts indicate restriction applied
*by category*. RG 242 is seized foreign records — restricted wholesale, so nothing is
reviewed one at a time.

**n = 3 agencies, and one of them inverts.** Plausible, not established. Do not
generalize. **Falsified by:** an agency with known per-item review showing a flat ratio.

⚠️ **These ratios are stale and should not be cited until recomputed.** They were
produced before two corrections to `forensics.edit_intensity`: unreviewed records were
being counted as adjudicated, and batch-import timestamps were being counted as edits.
Both push in unknown directions — the RG 242 inversion in particular could be an artifact
of either. Recomputing needs the v1 backup shards for all three record groups.

### Agencies have distinguishable withholding signatures

RG 263 is ~98% (b)(1) National Security. A State Department sample (n=2,109) showed
107 (b)(1) against 46 (b)(6) — a materially different privacy-vs-security mix.

**Sample-based, not a full survey.** The obvious next study.

---

## Refuted

| # | Hypothesis | How it died |
|---|---|---|
| 1 | Declassification detectable as status change between snapshots | 4 independent tests, 0 changes |
| 2 | The 2013 CIA edit spike was a declassification campaign | 1,835 records share `2013-06-27T00:00:00` to the second at midnight — a bulk import. Composition: 3,763 unrestricted vs 4 restricted |
| 3 | The Oct-2018 CIA restricted wave was the April 2018 JFK release | No clustering near 2018-04-26. Actual event: 43 records machine-created in 4 seconds on 2018-09-27, hand-finished 2018-10-03 |
| 4 | `Other` meant a deed or conditional-transfer restriction | The note cites the CIA Information Act of 1984 |
| 5 | OCR/extracted text is retrievable from bulk data | Absent from both schemas; `digitalObjects` holds URLs only |

Five dramatic hypotheses, five refutations. Every surviving finding survived *because* the
boring explanation was chased down first.

---

## Open questions

See [`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md).
