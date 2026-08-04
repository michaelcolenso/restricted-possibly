# AGENTS.md

Operating instructions for AI agents and human investigators working in this repository.
Read this **before** the code. Compatible with the [agents.md](https://agentsmd.net)
convention; Claude Code, Cursor, Aider and similar tools should load it automatically.

**Purpose:** explore the National Archives Catalog bulk corpus (~917 GB, 551 record
groups, 5,150 collections) and surface non-obvious findings from metadata alone.

## Repo conventions

| Task | Command |
|---|---|
| Install | `pip install -e ".[dev]"` |
| Offline tests | `pytest -m "not network"` |
| Live bucket tests | `pytest -m network` |
| Lint + format | `ruff check . && ruff format .` |
| Types | `mypy` |
| CLI | `rp --help` |

- Library code in `src/restricted_possibly/`. Ad-hoc analysis belongs in `docs/` as
  narrative, not in the package.
- **Never commit corpus data.** `data/` is gitignored except `.gitkeep`. Shards are
  50 MB+ and vintages are hundreds of GB.
- Field names mirror NARA's camelCase deliberately (`naId`, `accessRestriction`). Ruff's
  N815 is disabled for this reason. Don't "fix" them.
- New findings go in `docs/FINDINGS.md` with a denominator, a replication count, and an
  explicit falsification condition. Refutations get equal billing — see `docs/FINDINGS.md`
  for the format.

**Read this first:** the techniques below are validated. The *hypotheses* that motivated them were almost all wrong — five dramatic theories, five refutations. Inherit the methods and the discipline, not the theories. Your job is to run the machinery on unexplored parts of the corpus and let it tell you what's there.

---

## 0. Stance — read before the technical sections

This section exists because the disposition mattered more than any individual method. The findings came from how the work was approached, not from cleverness about archives.

### Touch the data in the first minute

The instinct to reach for is: *stop explaining, go look.* When handed the API docs, the productive move was not summarizing them — it was firing a request at the endpoint and discovering it returned an HTML shell. That single act reframed the entire project (API → S3 bucket) and cost thirty seconds. Every subsequent turning point came the same way: list the bucket, range-get one record, enumerate the keys. **Documentation describes intent; the bytes describe reality.** Prefer the bytes.

Corollary: don't ask permission to look. Reconnaissance is cheap, reversible, and almost always changes the plan.

### Generate widely, then let contact kill most of it

The opening move was five or six distinct project ideas across the corpus, ranked. That breadth was correct — but **the ranking was wrong.** The idea placed first (term-frequency over OCR text) was demoted within two exchanges once the schema showed no OCR field anywhere. The idea placed second became the actual product.

So: produce many angles fast, hold every one of them loosely, and treat the ranking as a hypothesis that data will revise. Being wrong early and cheaply is the intended behavior. Enthusiasm is fuel; it is not evidence.

### Let the interesting thing pull you

The work followed genuine pull rather than a plan: an odd field name, a status vocabulary richer than expected, a value that didn't fit the schema. Following those produced more than any roadmap would have. The `Other` restriction code was noticed because it was *weird*, not because anything predicted it.

Trust that reaction. But — see §5 — weirdness is a reason to *investigate*, never a reason to *conclude*.

### Hold the *frame* loosely, not just the hypotheses

This is the failure that actually cost the most in the originating project, and it is subtle because it does not feel like a mistake while it is happening.

Mid-project the investigation was steered toward "covert" angles. That steer was read as *a category of subject matter* — secrecy, restriction flags, exemption codes — and everything afterward happened inside the `accessRestriction` field. Four consecutive hypotheses were killed there and the drilling continued, because the frame had silently defined what counted as interesting. Cheaper and equally rich directions (digitization gaps, coverage-date topology across 551 agencies, the authority-record graph) went untouched. They sit in §7 as "unexplored" solely because the frame never released.

Note the shape of it: the individual hypotheses were held loosely and killed on contact, exactly as intended. The *frame* was never once put up for review. Loose hypotheses inside a locked frame still produces tunnel vision.

**The correction: "covert" is an inference style, not a subject area.** The most covert result in the entire project touched no secrecy field at all — reading `recordHistory` timestamps to reconstruct an individual archivist's 90-minute working session. Edit timestamps are the most tedious metadata in the corpus. Read sideways, they exposed staffing, workflow, and three distinguishable classes of human and machine activity.

That same move generalizes everywhere:

| Field | Overt reading | Covert reading |
|---|---|---|
| `digitalObjects` presence | what is scanned | what was chosen not to be findable |
| `coverageStartDate/EndDate` | date ranges | when an agency's institutional memory begins and ends |
| scope-note length, missing `creators` | description quality | which holdings were buried by being processed badly |
| `physicalOccurrences` | shelf location | which material moved between facilities, and when |
| `recordHistory` timestamps (v1) | edit log | staffing levels, workflow, individual working sessions |

Held this way the tension disappears: you are not trading breadth against depth, because the covert lens is *what you apply to* the broad survey. The survey supplies the denominator; the lens supplies the question.

**Four mechanics to keep the frame honest:**

1. **Stopping rule on the frame.** Two consecutive refutations inside one field or theme trigger a mandatory step back — not "what is my next hypothesis here," but "is this frame the thing that is failing?" Hypotheses are cheap to kill and get killed routinely. Frames need an explicit trigger or they are never reviewed at all.
2. **Overt first, because it is the control group.** The originating project ran this backwards. The restricted-vs-unrestricted edit-intensity result only became interpretable once the unrestricted baseline existed, and the RG 242 inversion only surfaced because three agencies were compared. Descriptive breadth is not the boring prerequisite to the interesting work — it is what makes the interesting work mean anything.
3. **Require the denominator.** Any claim about withheld, anomalous, or restricted material must carry its ordinary counterpart in the same output. This forces breadth mechanically, without relying on anyone remembering to be broad.
4. **Name the pull.** Secrecy angles are attractive partly because they feel higher-status than counting scanned documents. That attraction is a bias operating on you in real time. An investigator who cannot feel it cannot correct for it — so say it out loud when you notice yourself steering.

### Hold two temperaments at once

The productive mode was explicitly framed mid-project as combining obsessive pattern-hunting with institutional verification standards. Both halves are load-bearing:

- The hunting half reads boring fields nobody reads, chases the anomaly, refuses to accept that a null result means nothing is there, and asks what the *absence* of something implies.
- The verification half demands a baseline, a control, a replication across agencies, and an external ground-truth check before anything is called a finding.

Hunting without verification produces conspiracy. Verification without hunting produces a competent, boring summary of a schema. The value is in the tension.

### Report refutations with the same energy as discoveries

Five hypotheses died in this project. Each death was written up plainly and immediately — including one where the correction was to a claim made two messages earlier. This is not throat-clearing or hedging; **a refutation is a finding**, and it saves the next person the same detour. State clearly what is established, what is suggested, and what is merely a hypothesis with n=1.

Never let a satisfying narrative outrun the evidence. The most interesting result here — a covert operation described in full and closed by statute — is interesting precisely *because* the boring explanation was chased down and turned out to be the real one.

### Practical register

Move fast, narrate briefly, show the actual output. When something is checked and it changes the picture, say so directly rather than smoothing it over. When a step is expensive (a 180 GB record group, a per-object crawl), say that before starting it, not after.

---

## 1. Access — verified working, no credentials

Public S3 bucket, unsigned requests. No AWS account, no API key, no rate limit.

```python
import boto3
from botocore import UNSIGNED
from botocore.config import Config
s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
BUCKET = 'nara-national-archives-catalog'
```

`pip install boto3 --break-system-packages`

**Do not use the Catalog API for bulk work.** `https://catalog.archives.gov/api/v2/` requires a key issued by hand via email to `Catalog_API@nara.gov`. The undocumented `/proxy/records/search` path answers unauthenticated but throttles to HTML-shell responses within a few requests. Both are strictly worse than S3 for anything at scale. The API's only unique value is OCR/extracted text (see §3).

### Layout

```
descriptions/record-groups/rg_{N}/rg_{N}-{0..400}.jsonl   # 551 RGs, federal agencies
descriptions/collections/coll_{CODE}/                      # 5,150 presidential/donated
authority-records/{person,organization,geographic-reference,
                   topical-subject,specific-records-type}/  # linked entities
backups/descriptions{YYYYMMDD}/                            # 3 historical vintages, v1 schema
zip/nac_export_authorities_{DATE}.zip                      # ~45 MB authority snapshots
```

Shard count is always 400 — it's a hash partition, not a volume signal. **Use bytes, not shard count**, to size a record group.

### Largest record groups (bytes, descriptions/ only)

| RG | GB | Agency |
|---|---|---|
| 64 | 180.4 | National Archives itself |
| 29 | 96.6 | Census Bureau |
| 24 | 79.2 | Naval Personnel |
| 146 | 54.7 | (unresolved) |
| 147 | 49.3 | Selective Service |
| 85 | 43.5 | Immigration & Naturalization |
| 242 | 43.0 | Foreign Records Seized |
| 94 | 37.6 | Adjutant General (pre-1917) |
| 21 | 35.6 | District Courts |
| 69 | 26.3 | Works Progress Administration |
| 15 | 22.3 | Veterans Affairs |
| 109 | 19.7 | Confederate Records |
| 26 | 18.1 | Coast Guard |
| 59 | 18.1 | State Department |
| 407 | 12.3 | Adjutant General |
| 127 | 12.0 | Marine Corps |
| 111 | ~ | Signal Corps (photography) |
| 263 | ~ | CIA — fully surveyed, see §6 |

RG numbers run 1–999 non-contiguously. Titles are not in the bucket layout; resolve them from any record's `ancestors[]` entry where `levelOfDescription == 'recordGroup'`.

---

## 2. Two schemas — this trips everything up

### v2 (current, `descriptions/`) — JSONL, one record per line

```json
{"record": {"naId": 472515744, "title": "...", "accessRestriction": {...}, "ancestors": [...]}}
```

Verified full key set (RG 263 sample):
`accessRestriction, accessionNumbers, ancestors, arrangement, audiovisual, broadcastDates, coverageEndDate, coverageStartDate, creators, dataControlGroup, digitalObjects, editStatus, generalNotes, generalRecordsTypes, inclusiveEndDate, inclusiveStartDate, levelOfDescription, localIdentifier, naId, physicalOccurrences, productionDates, recordType, scaleNote, scopeAndContentNote, soundType, subjects, title, useRestriction, variantControlNumbers`

### v1 (`backups/descriptions{DATE}/`) — different everything

- Wrapper is **malformed JSON**: `{[ {...}, {...} ]}`. Strip the outer braces:
  ```python
  raw = open(path, encoding='utf-8', errors='replace').read().strip()
  if raw.startswith('{[') and raw.rstrip().endswith(']}'):
      raw = raw[1:raw.rstrip().rindex('}')]
  arr = json.loads(raw)
  ```
- Nested under `description.{series|fileUnit|item|...}`, with controlled terms as `{"naId":..., "termName":...}` objects rather than bare strings.
- Vintages: `descriptions20211206`, `descriptions20220420`, `descriptions20221221`.
- **Coverage is partial.** RG 59 and RG 85 are absent from the 2021 backup entirely. Always check `KeyCount` before assuming a group exists in a vintage.

### `naId` is stable across schema versions. It is your only reliable join key.

### ⚠ `recordHistory` exists ONLY in v1

The v1 schema carries per-record edit history — `recordHistory.created`, `changed.modification[]` (array, multiple edits), `broughtUnderEdit`, `approved`, all timestamped to the second. **This field was dropped in v2 and is absent from all current data.**

Consequence: the timestamp forensics in §4 are only runnable against the 2021–2022 backups. Do not plan current-state work around them. If NARA restores the field in a future refresh, that unlocks the technique corpus-wide — worth re-checking each snapshot.

---

## 3. What is NOT in the corpus

Verified absent — don't burn time looking:

- **OCR / extracted text.** Not in v2, not in v1. `digitalObjects` holds *URLs* only. Page text requires crawling those URLs or using the API. Any "government ngrams" / term-frequency-over-time idea is a crawl-and-harvest project, not a bulk-data project. Budget accordingly or drop it.
- **Digital object binaries.** URLs only.
- **Public contributions** (tags, transcriptions, comments) are documented as part of the dataset but were not located in `descriptions/`. Verify before relying on them.

---

## 4. Techniques (validated)

### 4.1 Cheap reconnaissance — range-gets

Never download a 50 MB shard to see its schema. Pull the first N bytes and parse the first line:

```python
o = s3.get_object(Bucket=BUCKET, Key=key, Range='bytes=0-300000')
buf = o['Body'].read().decode('utf-8', 'replace')
rec = json.loads(buf[:buf.index('\n')])
```

Some single records exceed 1.5 MB (huge scope notes). If `buf.index('\n')` raises, widen the range — and note that an oversized first record is itself a signal worth examining.

### 4.2 Streaming with a prefilter

Full scans of a record group are I/O-bound on JSON parsing, not network. Prefilter on the raw line before parsing:

```python
for line in io.TextIOWrapper(obj['Body'], encoding='utf-8', errors='replace'):
    if '"Restricted' not in line:      # cheap substring reject
        continue
    rec = json.loads(line)['record']   # only parse survivors
```

This made a 400-shard RG 263 pass tractable. Scale it with checkpointing for the 100 GB+ groups — do not attempt RG 64 or RG 29 interactively.

**Count what you skip.** One malformed line should not abort a 400-shard pass, but a silently dropped record shrinks the denominator of every rate computed from the scan while the run still looks complete. `corpus.ScanStats` carries the parse-failure count through `stream_shard`/`stream_group` and out via `Summary.parse_failures`. Check it before publishing any figure; non-zero means every count is a lower bound and must be reported as one.

### 4.3 Restriction inventory (the core product)

Extract every withheld description. `accessRestriction` has a clean controlled vocabulary:

- `status`: `Unrestricted` | `Restricted - Possibly` | `Restricted - Partly` | `Restricted - Fully` | absent
- `specificAccessRestrictions[].restriction`: `FOIA (b)(1) National Security`, `FOIA (b)(3) Statute`, `FOIA (b)(6) Personal Information`, `Other`, `John F. Kennedy Assassination Records Collection Act`
- `specificAccessRestrictions[].securityClassification`: e.g. `Top Secret`
- `note`: **free text — this is where the actual legal basis lives**

**Capture `note` and `securityClassification`.** The code that produced `withheld_rg_263.csv` omitted both, and that was a real defect: the restriction code `Other` is meaningless on its own, while the note said the records were statutorily exempt from FOIA *and* MDR. Fields to emit per row:

`naId, recordGroup, level, status, exemptions, securityClassification, note, coverageStart, coverageEnd, mediaType, containers, location, title`

Emit `note` **untruncated**. The qualification that makes a code interpretable can sit anywhere in it, and a cut-off statute is worse than no statute. `mediaType`, `containers`, and `location` come from `physicalOccurrences` (`mediaOccurrences[].specificMediaType` / `.containerId`, `referenceUnits[].name`) — a naId without a facility and a container is not yet something a person can request.

Interpretation notes:
- `Restricted - Possibly` means "not yet reviewed," not "withheld." It is a processing-backlog marker. Treat as a separate class.
- Records with **absent** status are frequently legacy 2001 catalog-migration imports, never edited. Exclude them from denominators or you inflate every rate.
- `useRestriction` ≠ `accessRestriction`. The former is copyright/reproduction; the latter is secrecy. Never conflate.
- Withholding is described at series *and* fileUnit level. Normalize by `levelOfDescription` before comparing across groups.

### 4.4 Write-once property (established)

Restriction status does **not** mutate. Four independent tests on RG 263:

- 2021→2022 snapshot diff, 9,985 shared naIds: zero status changes (only 10 absent→`Unrestricted`, i.e. field backfill)
- Oct-2018 batch of 33 records: 33/33 identical in 2025
- All 149 records restricted in 2021: 149/149 identical in 2025 (72/72 Partly, 70/70 Fully, 7/7 Possibly)

**Declassification does not appear as a status flip.** If material opens, it appears to arrive as *new* descriptions. Do not build a status-change monitor. **Do test whether write-once holds in other record groups** — it is established for one agency only, and a counterexample would be a significant finding.

### 4.5 Timestamp forensics (v1 backups only — see §2 warning)

`recordHistory` timestamps separate three distinct activity classes:

| Signature | Meaning |
|---|---|
| Many records, identical timestamp, `T00:00:00` | Automated batch import |
| Clusters of ~45 records at real times, seconds apart | Human running a bulk tool interactively |
| Steady one-record-per-20–40s over hours | Archivist hand-working a queue |

Verified examples: `2013-06-27T00:00:00` × 1,835 records (batch); `2015-11-20T17:18:21` × 45 (tool); `2018-10-03` 09:45→11:12, 85 records at ~20–40s intervals (human).

Use the batch signature as a **noise filter** — bulk imports dominate raw edit counts and mean nothing. Human-edited restricted records are the high-signal subset.

Secondary finding: mean modifications per record differed by restriction status, but **inconsistently across agencies** — RG 263 1.04 open / 1.52 restricted, RG 111 2.19 / 4.08, RG 242 1.15 / 1.01 (inverted). Working interpretation: elevated edit counts indicate *individually adjudicated* restriction; flat or inverted counts indicate *categorical* restriction applied wholesale. RG 242 (seized foreign records) restricts by category, hence no per-record review. **This is a hypothesis, not a result — n=3 agencies.** ⚠️ It is also **stale**: those numbers were computed before `edit_intensity` stopped counting unreviewed records as adjudicated and stopped counting batch-import stamps as edits. Recompute from the v1 shards before citing them.

---

## 5. Epistemic protocol — the actually important part

The corpus rewards pattern-hunting and punishes credulity. Every anomaly encountered so far had a mundane explanation. Follow this or you will publish nonsense.

1. **Boring explanation first, always.** Archives have prosaic causes for nearly everything: grant cycles, digitization contracts, systems migrations, one archivist's project, schema changes. Escalate only after the boring option is ruled out.
2. **Anomaly ⇒ read the free-text field.** The `Other` restriction code looked like a scandal. `accessRestriction.note` explained it in one sentence. Scope notes and general notes routinely contain the answer. Look before theorizing.
3. **Replicate across ≥3 record groups before generalizing.** The edit-intensity finding held in two agencies and inverted in the third. One record group is an anecdote.
4. **Check whether a field exists in the schema you're actually querying.** The `recordHistory` trap: an entire technique built on v1 data, silently inapplicable to v2. Enumerate keys first.
5. **Distinguish processing events from release events.** Metadata records when NARA *touched* something. It does not record when the public *got* something. Newly described ≠ newly opened.
6. **Validate against external ground truth before claiming significance.** A metadata spike means nothing until it lines up with a documented event. Two external hypotheses were tested (2013 spike → bulk import; April 2018 JFK release → no timestamp clustering) and both failed. That is the process succeeding.
7. **Small samples mislead on rates.** 10k-record sample suggested ~5% restricted in RG 263; the full 26,858-record pass gave ~7%.
8. **Two refutations in one frame ⇒ review the frame, not the hypothesis.** Killing hypotheses is routine and feels like progress; it can mask the fact that the whole line of inquiry is barren. See §0.
9. **Record refutations explicitly.** They are findings and they stop the next person repeating the work.

---

## 6. Dead ends — do not repeat

| Hypothesis | Outcome |
|---|---|
| Declassification detectable as status change between snapshots | **Refuted**, 4 tests |
| 2013 CIA edit spike = declassification campaign | **Refuted** — 1,835 records sharing `2013-06-27T00:00:00`; bulk import, 3,763 unrestricted vs 4 restricted |
| Oct-2018 CIA restricted wave = April 2018 JFK release | **Refuted** — no clustering near 2018-04-26; actual event was 2018-10-03 hand-processing |
| `Other` restriction code = deed/conditional transfer | **Refuted** — CIA Information Act of 1984 statutory exemption |
| OCR text retrievable from bulk data | **Refuted** — absent from both schemas |

### Settled context for RG 263 (survey complete)

1,359 adjudicated withholdings of 26,858 scanned (5.6% against 1,359 restricted + 23,118 unrestricted). Status: 1,080 Partly / 279 Fully, plus 509 `Restricted - Possibly` (never reviewed) and 1,872 with no status — both held out of the rate per §4.3. Exemptions: 1,293 (b)(1) National Security, 27 `Other`, 6 (b)(3), 5 JFK Act, 4 (b)(6). Levels: 1,247 fileUnit / 112 series.

An earlier pass reported 1,868 (~7%) by counting the unreviewed backlog as withheld. Do not reintroduce that: it inflates the numerator by 37% and puts a processing queue inside a secrecy statistic.

The 27 `Other` records: 25 are the CIA's Guatemala operations (PBFORTUNE, PBSUCCESS, PBHISTORY, Lincoln Station, cryptonyms KUHOOK/FJHOPEFUL/Calligeris), naIds 5956115–5956141, most `Top Secret`, most `Restricted - Fully`. Withheld under the **CIA Information Act of 1984** — exempt from FOIA search/review *and* from MDR under E.O. 13526 §3.5(a)(2). **Not FOIA-able; do not advise anyone to file on them.** The other two are the Nazi War Crimes second release (naId 640447) and the *open* Guatemala series (naId 6106938), redacted by CIA before transfer — neither is a statutory exemption, and only the `note` column tells them apart.

Open thread worth pursuing: every one of those 25 carries a note stating that declassified copies of selected documents may appear in the open series *Records Relating to Activities in Guatemala, 1949–1996* (naId 6106938), and that **NARA has never performed a comprehensive review to determine which**. Both sides are described in the catalog. Reconciling them is a tractable, genuinely unanswered research problem.

---

## 7. Suggested directions (unexplored)

Ranked by cost-to-value, all runnable on data already public:

1. **Extend the restriction inventory across all 551 groups.** The product is a public index of what the government has described and closed — naId, title, legal basis, classification, extent, location. Nothing like it exists. Start with mid-size groups (RG 242, 59, 109, 111, 127) before the 100 GB+ monsters.
2. **Cross-agency withholding signatures.** RG 263 is ~98% (b)(1). A State Dept sample showed a substantial (b)(6) share. Agencies have distinguishable secrecy profiles; quantify them.
3. **Hunt `Other` corpus-wide.** In RG 263 it flagged a statutorily-exempt covert operation. It is an escape hatch from the controlled vocabulary — wherever it appears, the note field will say something specific.
4. **Digitization gap.** `digitalObjects` presence × record group × `coverageStartDate` decade × `physicalOccurrences` location. Purely descriptive, no temporal dependency, cheap.
5. **Coverage-date topology.** When each agency's paper trail starts and ends, across 551 groups — an organizational history of the federal government drawn from record existence alone.
6. **Description-quality gradient.** Missing `creators`, absent coverage dates, oversized or empty scope notes. Metadata about metadata reveals which holdings are well-processed and which were dumped.
7. **Authority-record graph.** `authority-records/person` and `organization` cross-referenced against descriptions — entity adjacencies no single record states.

---

## 8. Limits

Everything here is public-domain federal metadata. Two constraints:

- **Aggregate patterns about agencies are the product. Profiles of named private individuals are not.** RG 15 (veterans' pensions), RG 85 (immigration), and every `(b)(6) Personal Information` flag exist because living people and their descendants are in those files. The (b)(6) code is a signal to aggregate, not to drill down.
- **Cite the corpus.** NARA requests attribution: *National Archives Catalog, accessed [DATE] from https://registry.opendata.aws/nara-national-archives-catalog*.

---

## 9. Working scripts

In the working directory, reusable:

- `probe.py` — API/proxy probe with backoff; deep-scans a record for keys matching a needle list. Set `API_KEY` to switch to authenticated v2.
- `diff_restrictions.py` — v1↔v1 snapshot diff; status transitions, opened/closed/exemption-changed.
- `edit_history.py` — v1 timestamp forensics; creation/modification distributions by restriction bucket, batch-import detection.
- `inventory.py` — **the main tool.** One streaming pass over a record group: emits restriction inventory CSV + runs the write-once test against a v1 vintage. `python3 inventory.py rg_242 rg242_2021.json`. **Patch it to capture `note` and `securityClassification` before your first real run.**
