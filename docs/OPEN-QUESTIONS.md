# Open questions

Tractable problems on public data. Roughly ordered by ratio of interest to effort.

## 1. The Guatemala reconciliation

Every one of the 25 `Other`-coded PBSUCCESS-family series (naIds 5956115–5956141) carries
this general note:

> Copies of selected documents relating to PBFORTUNE, PBSUCCESS, and PBHISTORY from this
> series that have been declassified by the Central Intelligence Agency (CIA) may be found
> in the series "Records Relating to Activities in Guatemala, 1949–1996" (ARC Identifier
> 6106938). However, **a comprehensive review has not been performed to ascertain what
> specific records from this series have been declassified.**

NARA is stating plainly that nobody knows how much of the closed material has already been
released through the open series. Both sides are described in the catalog. The closed
series have known physical extents (11 ft 7 in of Subject Files, 5 ft 3 in of incoming
cables, etc.) at College Park.

**Why it's tractable:** it's a set-comparison problem between two described series, not a
FOIA fight. **Why it matters:** it would quantify the actual gap between "withheld" and
"unavailable" for a specific, historically significant operation.

## 2. Does write-once hold outside RG 263?

The strongest established finding rests on one agency. Run `write_once_check` against
RG 242 and RG 109 (both present in the 2021 vintage; note RG 59 and RG 85 are **not**).
A single counterexample would reopen the declassification-monitoring question entirely.

## 3. Where else does `Other` appear, and what do its notes say?

In RG 263 it flagged a statutorily exempt covert operation. It's an escape hatch from the
controlled vocabulary, and in that one record group the `note` field explained every
instance — 25 citing the CIA Information Act, one the Nazi War Crimes acts, one a
pre-transfer redaction.

**Whether that holds anywhere else is the hypothesis this sweep tests**, not a premise it
starts from. An `Other` record with a missing or uninformative note is the interesting
outcome: it would falsify the RG 263 finding's load-bearing claim (see `FINDINGS.md`) and
mean the code is a genuine void rather than a pointer. Record those separately from the
ones whose notes do explain. The sweep is cheap either way.

## 4. What is in the 100 GB+ record groups?

RG 64 (180 GB, the Archives documenting itself), RG 29 (Census, 97 GB), RG 24 (Naval
Personnel, 79 GB) are entirely unsurveyed. These need checkpointed batch runs.

## 5. Which record groups are missing from which vintages, and why?

RG 59 and RG 85 are absent from the 2021 backup. Systematically diffing vintage membership
would reveal whether this is partial-export noise or something structured.

## 6. Do "removed" naIds exist?

A 2021→2022 diff showed 15 added / 15 removed in one shard. Records *leaving* a public
catalog is the single most interesting event class available here, and it was never
chased. Needs a full-group diff, not a shard sample.

## 7. Reconcile description-level vs item-level restriction

Restriction is recorded at both series and fileUnit level. A series can be marked closed
while most folders inside it are open, and vice versa. Nobody has quantified the
disagreement rate.
