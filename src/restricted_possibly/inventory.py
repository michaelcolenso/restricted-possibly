"""Withholding inventory: what has been described and closed.

This is the core product. For any record group it emits one row per restricted
description, with the identifiers and legal grounds needed to act on it.

Design rule -- **always carry the denominator.** Every summary reports the
unrestricted baseline alongside the restricted count. A withholding rate is
uninterpretable without it, and requiring it structurally is what keeps an
investigation from tunnelling into the secrecy fields.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from . import corpus, schema

#: `(b)(6)` marks a withholding made to protect a living person or their
#: descendants. Per the limit in AGENTS.md 8, that code is a signal to
#: aggregate, not to drill down.
PERSONAL = "FOIA (b)(6) Personal Information"

#: Levels at which one description is plausibly one person -- a pension file,
#: an immigration case file. A `series` carrying (b)(6) describes a body of
#: records ("Name Files Under the Nazi War Crimes Act"), not an individual, so
#: it is already aggregate and stays intact.
PERSONAL_LEVELS = {"item", "fileUnit"}

REDACTED = "[(b)(6) personal information -- aggregate only]"


@dataclass
class Row:
    naId: str
    recordGroup: int | None
    level: str | None
    status: str | None
    exemptions: str
    securityClassification: str | None
    note: str
    coverageStart: int | None
    coverageEnd: int | None
    mediaType: str
    containers: str
    location: str
    title: str


@dataclass
class Summary:
    group: str
    scanned: int
    #: Adjudicated withholdings only. `unreviewed` is tracked separately.
    restricted: int
    unrestricted: int
    unreviewed: int
    no_status: int
    by_status: dict[str, int]
    by_exemption: dict[str, int]
    by_level: dict[str, int]
    #: Lines that could not be parsed and so never reached `scanned`. Non-zero
    #: means every count here is a lower bound -- report it or do not publish.
    parse_failures: int = 0
    #: Row-level `(b)(6)` records whose identifying fields were suppressed.
    #: They are still counted everywhere else in this summary.
    personal_redacted: int = 0

    @property
    def restricted_rate(self) -> float:
        """Excludes never-reviewed and status-absent records from the base."""
        base = self.restricted + self.unrestricted
        return self.restricted / base if base else 0.0


def build(
    group: str, limit_shards: int | None = None, redact_personal: bool = True
) -> tuple[list[Row], Summary]:
    """Single streaming pass over a record group.

    Rows are *adjudicated* withholdings only -- `Restricted - Fully` and
    `Restricted - Partly`. `Restricted - Possibly` means "not yet reviewed" and
    is reported separately as `Summary.unreviewed`; counting a processing
    backlog as withheld would overstate every rate built on this.

    Item- and fileUnit-level `(b)(6)` rows have their identifying and locating
    fields redacted by default, and are counted in `Summary.personal_redacted`.
    Run this over RG 15 or RG 85 without that and the output is a person-level
    index of veterans' pension and immigration files -- the exact artifact
    AGENTS.md 8 rules out. The rows stay, so the counts remain complete;
    what goes is the ability to walk from a row to a named individual's file.
    Pass `redact_personal=False` only with a reason.
    """
    rows: list[Row] = []
    status_ct: Counter[str] = Counter()
    exempt_ct: Counter[str] = Counter()
    level_ct: Counter[str] = Counter()
    scanned = unrestricted = no_status = personal_redacted = 0
    stats = corpus.ScanStats()

    for rec in corpus.stream_group(group, limit_shards=limit_shards, stats=stats):
        scanned += 1
        r = schema.parse_restriction(rec.get("accessRestriction"))
        if r.status is None:
            no_status += 1
            continue
        status_ct[r.status] += 1
        if r.status == "Unrestricted":
            unrestricted += 1
            continue
        if r.is_unreviewed:
            # `Restricted - Possibly` is a processing-backlog marker, not a
            # withholding decision. It stays in `by_status` and `unreviewed`,
            # and out of the withheld rows -- and so out of both the numerator
            # and the denominator of `restricted_rate`.
            continue
        if not r.is_restricted:
            continue

        level_ct[rec.get("levelOfDescription") or "?"] += 1
        # De-duplicated: `by_exemption` counts *descriptions* citing an
        # exemption, so it can be read against `restricted`. A description can
        # list the same restriction twice under different classifications --
        # RG 263 naId 305945 cites (b)(1) once as Top Secret and once as
        # Restricted Data -- and counting occurrences made that one record two.
        # The row keeps every entry; only the summary de-duplicates.
        for e in dict.fromkeys(r.exemptions):
            exempt_ct[e] += 1
        rgnum = next(
            (
                a.get("recordGroupNumber")
                for a in rec.get("ancestors", [])
                if a.get("levelOfDescription") == "recordGroup"
            ),
            None,
        )
        level = rec.get("levelOfDescription")
        personal = redact_personal and PERSONAL in r.exemptions and level in PERSONAL_LEVELS
        if personal:
            personal_redacted += 1

        row = Row(
            naId=str(rec.get("naId")),
            recordGroup=rgnum,
            level=level,
            status=r.status,
            exemptions="; ".join(r.exemptions),
            securityClassification=r.security_classification,
            coverageStart=schema.year(rec.get("coverageStartDate")),
            coverageEnd=schema.year(rec.get("coverageEndDate")),
            title=(rec.get("title") or "").replace("\n", " ")[:300],
            # Never truncated: the note *is* the legal basis, and the
            # qualification that makes a code like `Other` interpretable
            # can sit anywhere in it.
            note=(r.note or "").replace("\n", " "),
            **schema.physical(rec),
        )
        if personal:
            # Structure stays (the counts must still add up); the identifying
            # and locating fields go.
            row.title = row.note = REDACTED
            row.containers = row.location = REDACTED
        rows.append(row)

    unreviewed = status_ct.get(schema.UNREVIEWED, 0)
    summary = Summary(
        group=group,
        scanned=scanned,
        restricted=len(rows),
        unrestricted=unrestricted,
        unreviewed=unreviewed,
        no_status=no_status,
        by_status=dict(status_ct.most_common()),
        by_exemption=dict(exempt_ct.most_common()),
        by_level=dict(level_ct.most_common()),
        parse_failures=stats.parse_failures,
        personal_redacted=personal_redacted,
    )
    if not scanned and not stats.parse_failures:
        # A misspelled or absent group streams nothing, and every count below
        # is then a truthful description of nothing: 0 restricted, 0
        # unrestricted, a 0.00% rate. That is indistinguishable from a real
        # zero-withholding survey, so refuse to hand it back. The CLI checks
        # the shard list first and says so more helpfully; this guards the
        # library path, which is the one AGENTS.md 9 points people at.
        raise ValueError(
            f"no records scanned for {group!r} -- check the group name. "
            "Nothing was read, so every count would be a description of nothing."
        )
    return rows, summary


def write_csv(rows: list[Row], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[f.name for f in Row.__dataclass_fields__.values()])
        w.writeheader()
        w.writerows(asdict(r) for r in rows)
    return path


def write_once_check(
    old_restricted: dict[str, str], current: dict[str, str | None]
) -> dict[str, int]:
    """Compare 2021-vintage restricted naIds against their current status.

    Established for RG 263 across four independent tests: restriction status
    does not mutate. Declassification does not appear as a status flip. A
    counterexample in another record group would be a significant finding --
    which is exactly why this check is worth running everywhere.
    """
    out: Counter[str] = Counter()
    for na, old in old_restricted.items():
        new = current.get(na, "(absent from current)")
        out[f"{old} -> {new}"] += 1
    return dict(out.most_common())
