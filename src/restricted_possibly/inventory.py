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

    @property
    def restricted_rate(self) -> float:
        """Excludes never-reviewed and status-absent records from the base."""
        base = self.restricted + self.unrestricted
        return self.restricted / base if base else 0.0


def build(group: str, limit_shards: int | None = None) -> tuple[list[Row], Summary]:
    """Single streaming pass over a record group.

    Rows are *adjudicated* withholdings only -- `Restricted - Fully` and
    `Restricted - Partly`. `Restricted - Possibly` means "not yet reviewed" and
    is reported separately as `Summary.unreviewed`; counting a processing
    backlog as withheld would overstate every rate built on this.
    """
    rows: list[Row] = []
    status_ct: Counter[str] = Counter()
    exempt_ct: Counter[str] = Counter()
    level_ct: Counter[str] = Counter()
    scanned = unrestricted = no_status = 0

    for rec in corpus.stream_group(group, limit_shards=limit_shards):
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
        for e in r.exemptions:
            exempt_ct[e] += 1
        rgnum = next(
            (
                a.get("recordGroupNumber")
                for a in rec.get("ancestors", [])
                if a.get("levelOfDescription") == "recordGroup"
            ),
            None,
        )
        rows.append(
            Row(
                naId=str(rec.get("naId")),
                recordGroup=rgnum,
                level=rec.get("levelOfDescription"),
                status=r.status,
                exemptions="; ".join(r.exemptions),
                securityClassification=r.security_classification,
                coverageStart=schema.year(rec.get("coverageStartDate")),
                coverageEnd=schema.year(rec.get("coverageEndDate")),
                title=(rec.get("title") or "").replace("\n", " ")[:300],
                note=(r.note or "").replace("\n", " ")[:1000],
            )
        )

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
