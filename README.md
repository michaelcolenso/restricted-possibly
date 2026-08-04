# restricted-possibly

> **`Restricted - Possibly`** is a real status value in the National Archives Catalog.
> It means nobody has looked yet.

Survey tooling for the **National Archives Catalog bulk corpus** — ~917 GB of federal
archival metadata covering 551 record groups and 5,150 collections, published to a public
S3 bucket that requires **no AWS account, no API key, and has no rate limit.**

Most people who want this data reach for NARA's Catalog API, hit a key request that's
processed by hand over email, and then hit throttling. The bucket is strictly better for
anything at scale, and almost nobody uses it.

```bash
pip install -e .
rp groups --sizes          # 551 record groups, ranked by volume
rp peek rg_263             # schema + size of one group, via a 300 KB range-get
rp inventory rg_263        # every withheld description → CSV
```

---

## What this actually does

It builds a **withholding inventory**: for any record group, every description NARA has
catalogued *and closed* — with the naId, title, legal basis (the full, untruncated
restriction note), security classification, media type, container ids, and the NARA
facility that holds it.

That artifact does not exist anywhere. It matters because the hardest part of a FOIA
request is naming the record you want, and NARA has already published the names.

Running it against RG 263 (CIA) found 1,359 withheld descriptions out of 26,858 — plus
509 more that nobody has reviewed yet — and inside them, this:

> 25 series covering the CIA's Guatemala operations — **PBFORTUNE**, **PBSUCCESS**,
> **PBHISTORY**, Lincoln Station, cryptonyms KUHOOK / FJHOPEFUL / Calligeris — described
> in full, mostly Top Secret, mostly `Restricted - Fully`, and withheld under a
> restriction code of **`Other`** rather than any FOIA exemption.
>
> The reason is in the `note` field: the **CIA Information Act of 1984** exempts these
> records from FOIA search and review *and* from Mandatory Declassification Review under
> E.O. 13526 §3.5(a)(2). **Both doors are closed by statute.** Do not file on them.
>
> Every one of those 25 also carries a note stating that declassified copies of selected
> documents may appear in the open series *Records Relating to Activities in Guatemala,
> 1949–1996* (naId 6106938) — and that **NARA has never performed a comprehensive review
> to determine which.** Both sides are described in the catalog. Reconciling them is an
> open, tractable research problem. See [`docs/OPEN-QUESTIONS.md`](docs/OPEN-QUESTIONS.md).

That's one record group of 551.

---

## Install

Requires Python 3.11+.

```bash
git clone https://github.com/OWNER/restricted-possibly
cd restricted-possibly
pip install -e ".[dev]"        # or: uv sync --extra dev
pytest -m "not network"        # offline suite
```

No credentials at any point. The client is hard-coded to unsigned requests and every
operation is read-only.

---

## The corpus in five minutes

### Layout

```
descriptions/record-groups/rg_{N}/rg_{N}-{0..400}.jsonl   551 groups, federal agencies
descriptions/collections/coll_{CODE}/                     5,150 presidential/donated
authority-records/{person,organization,geographic-reference,
                   topical-subject,specific-records-type}/
backups/descriptions{YYYYMMDD}/                           3 historical vintages (v1 schema)
zip/nac_export_authorities_{DATE}.zip                     ~45 MB authority snapshots
```

**Shard count is always ~400.** It's a hash partition, not a volume signal — use bytes.

### Largest record groups

| RG | GB | Agency |
|---:|---:|---|
| 64 | 180.4 | National Archives itself |
| 29 | 96.6 | Census Bureau |
| 24 | 79.2 | Naval Personnel |
| 147 | 49.3 | Selective Service |
| 85 | 43.5 | Immigration & Naturalization |
| 242 | 43.0 | Foreign Records Seized |
| 94 | 37.6 | Adjutant General (pre-1917) |
| 21 | 35.6 | District Courts |
| 69 | 26.3 | Works Progress Administration |
| 15 | 22.3 | Veterans Affairs |
| 109 | 19.7 | Confederate Records |
| 59 | 18.1 | State Department |
| 263 | — | CIA — **surveyed**, see `docs/FINDINGS.md` |

### Two schemas, and the trap in between

**v2** (current) — JSONL, flat, bare strings.
**v1** (backups, 2021–2022) — one malformed blob per shard wrapped as `{[ ... ]}`, nested
under `description.{series|fileUnit|...}`, controlled terms as `{naId, termName}` objects.
Coverage is partial: RG 59 and RG 85 are **absent** from the 2021 vintage entirely.

`naId` is stable across both. It's your only reliable join key.

> ⚠️ **`recordHistory` exists only in v1.** Per-record edit timestamps were dropped in the
> v2 migration. All timestamp forensics are limited to the 2021–2022 vintages. There's a
> live test (`test_v2_schema_has_no_record_history`) that will fail loudly if NARA ever
> restores it — which would unlock the technique corpus-wide.

### What is *not* in the corpus

- **OCR / extracted text.** Not in either schema. `digitalObjects` holds URLs only. Any
  term-frequency-over-time idea is a crawl-and-harvest project, not a bulk-data project.
- **Digital object binaries.** URLs only.
- **Public contributions** (tags, transcriptions, comments) are documented as part of the
  dataset but were not located under `descriptions/`. Verify before relying on them.

---

## Techniques

### Range-get before you download

```python
from restricted_possibly import corpus

rec = corpus.peek(corpus.shards("rg_263")[0].key)  # 300 KB, not 50 MB
```

Some single records exceed 1.5 MB. If `peek` returns `None`, widen the window — and note
that an oversized record is itself worth investigating.

### Prefilter before you parse

Full scans are bound by JSON parse cost, not network:

```python
for rec in corpus.stream_group("rg_263", prefilter='"Restricted'):
    ...  # only lines that survive the substring test get parsed
```

### Always carry the denominator

`inventory.Summary` reports the unrestricted baseline alongside every restricted count,
and `restricted_rate` excludes never-reviewed and status-absent records from its base.
This is deliberate: a withholding rate is uninterpretable without its counterpart, and
enforcing it structurally is what stops an investigation from tunnelling into the secrecy
fields. The full 26,858-record pass of RG 263 gives 1,359 adjudicated withholdings
against 23,118 unrestricted — 5.6% — with 509 never-reviewed and 1,872 status-absent
records held out of both the numerator and the base.

### Timestamp forensics (v1 only)

Three activity classes separate cleanly by signature:

| Signature | Meaning |
|---|---|
| Many records, identical stamp, `T00:00:00` | Automated batch import |
| Clusters of ~45 at real clock time, seconds apart | Human running a bulk tool |
| One record per 20–40s, sustained for hours | Archivist working a queue |

Verified: `2013-06-27T00:00:00` ×1835 (batch), `2015-11-20T17:18:21` ×45 (tool),
2018-10-03 09:45→11:12 at 20–40s intervals (a person, one sitting).

Use the batch signature as a **noise filter** — bulk imports dominate raw edit counts and
mean nothing.

```bash
rp sessions path/to/rg_263-0.json    # reconstruct working sessions
```

---

## Established findings

**Restriction status is write-once.** Four independent tests on RG 263 — a 2021→2022
snapshot diff across 9,985 shared naIds, a 33-record batch, and all 149 records restricted
in 2021 — produced **zero** status changes over four years. Declassification does not
appear as a status flip; released material seems to arrive as *new* descriptions.

Do not build a status-change monitor. **Do** run `write_once_check` on other record
groups — a counterexample would be a significant finding, and it's established for exactly
one agency.

**Agencies have distinguishable withholding signatures.** RG 263 is ~98% FOIA (b)(1)
National Security. A State Department sample showed a substantial (b)(6) Personal
Information share. Quantifying this across all 551 groups is the obvious next study.

Full detail, including five refuted hypotheses, in [`docs/FINDINGS.md`](docs/FINDINGS.md).

---

## Refuted — don't repeat these

| Hypothesis | Outcome |
|---|---|
| Declassification detectable as status change between snapshots | **Refuted**, 4 tests |
| 2013 CIA edit spike = declassification campaign | **Refuted** — 1,835 records share one midnight timestamp; bulk import |
| Oct-2018 CIA restricted wave = the April 2018 JFK release | **Refuted** — no clustering near 2018-04-26 |
| `Other` restriction code = deed or conditional transfer | **Refuted** — CIA Information Act of 1984 |
| OCR text retrievable from bulk data | **Refuted** — absent from both schemas |

Five dramatic theories, five refutations. The findings that survived did so *because* the
boring explanation was chased down first. If you're working on this corpus, read
[`AGENTS.md`](AGENTS.md) before you read the code.

---

## Where to go next

Ranked by cost-to-value, all runnable on public data:

1. **Extend the inventory to all 551 groups.** Start mid-size (RG 242, 59, 109, 111, 127)
   before the 100 GB+ groups. RG 64 and RG 29 need checkpointing, not an interactive run.
2. **Cross-agency withholding signatures.** Quantify the (b)(1)/(b)(6)/(b)(3) mix per agency.
3. **Hunt `Other` corpus-wide.** It's an escape hatch from the controlled vocabulary; the
   `note` field always explains it.
4. **Digitization gap.** `digitalObjects` presence × record group × coverage decade ×
   physical location. No temporal dependency, cheap.
5. **Coverage-date topology.** When each agency's paper trail starts and ends — an
   organizational history of the federal government drawn from record existence alone.
6. **Description-quality gradient.** Missing creators, absent dates, empty scope notes.
   Metadata about metadata reveals which holdings were buried by being processed badly.
7. **Authority-record graph.** Person/organization entities cross-referenced against
   descriptions — adjacencies no single record states.

---

## Ethics

Everything here is public-domain federal metadata. Two constraints, and they aren't
decoration:

**Aggregate patterns about agencies are the product. Profiles of named private
individuals are not.** RG 15 (veterans' pensions), RG 85 (immigration), and every
`FOIA (b)(6) Personal Information` flag exist because living people and their descendants
are in those files. Treat (b)(6) as a signal to aggregate, not to drill down.

**Don't launder speculation as research.** This corpus is unusually good at generating
compelling narratives that turn out to be bulk imports. See the refutation table.

---

## Attribution

NARA requests that users of the dataset cite it:

> National Archives Catalog, accessed [DATE] from
> https://registry.opendata.aws/nara-national-archives-catalog

Archival metadata is a work of the U.S. federal government and is in the public domain,
with rare exceptions noted in each record's `useRestriction` field. Note that
`useRestriction` (copyright) and `accessRestriction` (secrecy) are different things and
are routinely conflated.

Code in this repository is MIT licensed. See [`LICENSE`](LICENSE).

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). The short version: new findings need a
denominator, a replication across ≥3 record groups, and an explicit statement of what
would falsify them. Refutations are as welcome as discoveries and get the same treatment
in `docs/FINDINGS.md`.
