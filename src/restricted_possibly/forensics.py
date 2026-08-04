"""Activity forensics from per-record edit timestamps.

.. warning::
   ``recordHistory`` exists **only in the v1 backup vintages** (2021-2022). It
   was dropped in the v2 migration. Everything here operates on locally
   downloaded v1 shards, not on current data.

Three activity classes are separable by timestamp signature:

===============================================  ==========================
Signature                                        Meaning
===============================================  ==========================
Many records, identical stamp, ``T00:00:00``     Automated batch import
Clusters of ~45, real clock time, seconds apart  Human running a bulk tool
One record per 20-40s, sustained for hours       Archivist working a queue
===============================================  ==========================

Verified instances: ``2013-06-27T00:00:00`` x1835 (batch);
``2015-11-20T17:18:21`` x45 (tool); 2018-10-03 09:45->11:12, 85 records at
20-40s intervals (human).

Use the batch signature as a **noise filter**. Bulk imports dominate raw edit
counts and mean nothing; hand-edited records are the high-signal subset.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from . import schema


@dataclass
class Burst:
    timestamp: str
    count: int

    @property
    def is_midnight(self) -> bool:
        return self.timestamp.endswith("T00:00:00")

    @property
    def classification(self) -> str:
        if self.is_midnight and self.count > 50:
            return "automated batch import"
        if self.count > 5:
            return "interactive bulk tool"
        return "manual edit"


def bursts(items: list[dict[str, Any]], min_count: int = 5) -> list[Burst]:
    """Identical-to-the-second timestamps, descending by frequency."""
    ct: Counter[str] = Counter()
    for _level, body in schema.iter_v1_descriptions(items):
        ct.update(schema.v1_modifications(body))
    return [Burst(t, n) for t, n in ct.most_common() if n >= min_count]


def batch_timestamps(items: list[dict[str, Any]], threshold: int = 50) -> set[str]:
    """Timestamps to treat as machine noise when filtering."""
    return {b.timestamp for b in bursts(items, min_count=threshold) if b.is_midnight}


def sessions(
    items: list[dict[str, Any]], gap_seconds: int = 300, min_edits: int = 10
) -> list[dict[str, Any]]:
    """Contiguous human working sessions (non-midnight, steady cadence).

    Returns dicts with start, end, count and the naIds touched -- i.e. what one
    person did in one sitting.
    """
    from datetime import datetime

    events: list[tuple[datetime, str]] = []
    for _level, body in schema.iter_v1_descriptions(items):
        na = str(body.get("naId"))
        for t in schema.v1_modifications(body):
            if t.endswith("T00:00:00"):
                continue  # machine
            try:
                events.append((datetime.fromisoformat(t), na))
            except ValueError:
                continue
    events.sort()

    out: list[dict[str, Any]] = []
    cur: list[tuple[datetime, str]] = []
    for ev in events:
        if cur and (ev[0] - cur[-1][0]).total_seconds() > gap_seconds:
            if len(cur) >= min_edits:
                out.append(_session(cur))
            cur = []
        cur.append(ev)
    if len(cur) >= min_edits:
        out.append(_session(cur))
    return out


def _session(events) -> dict[str, Any]:
    span = (events[-1][0] - events[0][0]).total_seconds()
    return {
        "start": events[0][0].isoformat(),
        "end": events[-1][0].isoformat(),
        "count": len(events),
        "duration_minutes": round(span / 60, 1),
        "mean_interval_seconds": round(span / max(len(events) - 1, 1), 1),
        "naIds": sorted({na for _, na in events}),
    }


def edit_intensity(items: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Mean modifications per record, split by restriction bucket.

    Interpretation (hypothesis, n=3 agencies): elevated edit counts on
    restricted records indicate *individually adjudicated* restriction;
    flat or inverted counts indicate *categorical* restriction applied
    wholesale. RG 263 1.04/1.52, RG 111 2.19/4.08, RG 242 1.15/1.01 (inverted;
    seized foreign records are restricted by category, so nothing is reviewed
    one at a time).

    Do not generalize from a single record group.
    """
    buckets: dict[str, list[int]] = defaultdict(list)
    for _level, body in schema.iter_v1_descriptions(items):
        r = schema.parse_restriction(body.get("accessRestriction"))
        key = "restricted" if r.is_restricted else ("open" if r.status else "no_status")
        buckets[key].append(len(schema.v1_modifications(body)))
    return {
        k: {
            "n": len(v),
            "mean_mods": round(sum(v) / len(v), 3) if v else 0.0,
            "never_edited_pct": round(100 * sum(1 for x in v if x == 0) / len(v), 1) if v else 0.0,
        }
        for k, v in sorted(buckets.items())
    }
