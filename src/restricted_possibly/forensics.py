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
One record per 20-40s, sustained for hours       Hand-paced editing
===============================================  ==========================

Verified instances: ``2013-06-27T00:00:00`` x1835 (batch);
``2015-11-20T17:18:21`` x45 (tool); 2018-10-03 09:45->11:12, 85 records at
20-40s intervals (hand-paced).

The third class separates *human* from *machine* cadence. It does not
identify a human: v1 carries no actor field, so concurrent editors are
indistinguishable from one editor working longer. See `sessions`.

Use the batch signature as a **noise filter**. Bulk imports dominate raw edit
counts and mean nothing; hand-edited records are the high-signal subset.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from . import schema

#: A midnight timestamp shared by at least this many records is a batch import.
#: One constant, used by both the filter and the label -- when they disagreed,
#: an event of exactly 50 was dropped from `edit_intensity` as machine noise
#: while `Burst.classification` still called it a manual edit.
BATCH_THRESHOLD = 50

#: Identical non-midnight stamps at or above this count are one bulk-tool run,
#: not a person typing. Shared by `Burst.classification` and `sessions`.
TOOL_THRESHOLD = 5


@dataclass
class Burst:
    timestamp: str
    count: int

    @property
    def is_midnight(self) -> bool:
        return self.timestamp.endswith("T00:00:00")

    @property
    def classification(self) -> str:
        if self.is_midnight and self.count >= BATCH_THRESHOLD:
            return "automated batch import"
        if self.count >= TOOL_THRESHOLD:
            return "interactive bulk tool"
        return "manual edit"


def timestamp_counts(items: list[dict[str, Any]]) -> Counter[str]:
    """Modification timestamps and their frequencies for one shard.

    The streaming primitive: a shard's parsed JSON is large, this Counter is
    small, so a caller can fold one of these per shard and drop each shard
    before loading the next. Burst classification is a frequency test and
    frequencies are only meaningful group-wide (see `sessions`), so the fold
    has to happen somewhere -- doing it on counts rather than on records is
    what keeps a 400-shard group inside memory.
    """
    ct: Counter[str] = Counter()
    for _level, body in schema.iter_v1_descriptions(items):
        ct.update(schema.v1_modifications(body))
    return ct


def bursts_from_counts(counts: Counter[str], min_count: int = TOOL_THRESHOLD) -> list[Burst]:
    """Identical-to-the-second timestamps, descending by frequency."""
    return [Burst(t, n) for t, n in counts.most_common() if n >= min_count]


def batch_timestamps_from_counts(
    counts: Counter[str], threshold: int = BATCH_THRESHOLD
) -> set[str]:
    """Timestamps to treat as machine noise when filtering."""
    return {b.timestamp for b in bursts_from_counts(counts, threshold) if b.is_midnight}


def tool_timestamps_from_counts(counts: Counter[str], threshold: int = TOOL_THRESHOLD) -> set[str]:
    """Non-midnight stamps repeated enough times to be one bulk-tool run.

    The single definition of "this was a tool, not a person," so `sessions`
    and the CLI's streaming path cannot drift apart on the boundary.
    """
    return {t for t, n in counts.items() if n >= threshold and not t.endswith("T00:00:00")}


def bursts(items: list[dict[str, Any]], min_count: int = TOOL_THRESHOLD) -> list[Burst]:
    """Single-shard convenience. For a whole group, fold `timestamp_counts`."""
    return bursts_from_counts(timestamp_counts(items), min_count)


def batch_timestamps(items: list[dict[str, Any]], threshold: int = BATCH_THRESHOLD) -> set[str]:
    """Single-shard convenience. For a whole group, fold `timestamp_counts`."""
    return batch_timestamps_from_counts(timestamp_counts(items), threshold)


def sessions(
    items: list[dict[str, Any]],
    gap_seconds: int = 300,
    min_edits: int = 10,
    max_identical: int = TOOL_THRESHOLD,
) -> list[dict[str, Any]]:
    """Contiguous **activity windows** of hand-paced editing.

    Returns dicts with start, end, count and the naIds touched.

    .. warning::
       A window is not a person. `recordHistory` records *when* a record was
       modified and never *by whom* -- there is no actor field anywhere in v1
       -- so these are grouped by time alone. Two archivists working the same
       afternoon within `gap_seconds` of each other merge into one window, and
       the result would report their combined edits as a single sitting. Read
       a window as "the desk was busy," not "someone was at it," and do not
       build staffing conclusions on the count of windows.

    Two machine signatures are removed first, not one. Midnight stamps are
    batch imports. Non-midnight stamps repeated `max_identical` times or more
    are one bulk-tool run -- the verified `2015-11-20T17:18:21` x45 event is
    the type case, and left in it reads as a 45-edit window at zero-second
    intervals, which is the opposite of the hand-worked cadence this looks for.
    """
    counts = timestamp_counts(items)
    machine = tool_timestamps_from_counts(counts, max_identical)
    return sessions_from_events(collect_events(items, machine), gap_seconds, min_edits)


def collect_events(items: list[dict[str, Any]], machine_stamps: set[str]) -> list[tuple[str, str]]:
    """`(timestamp, naId)` pairs for one shard, machine activity removed.

    Two pairs of strings per edit rather than the parsed record, so a caller
    can accumulate these across a whole group while holding one shard at a
    time. `machine_stamps` carries the group-wide bulk-tool timestamps, which
    cannot be identified from a single shard.

    **Every** ``T00:00:00`` stamp is dropped, regardless of how many records
    share it -- a stricter rule than `BATCH_THRESHOLD`, and deliberately so.
    Windows are built from *cadence*, and a midnight stamp is a date with no
    time of day recorded, so it carries no cadence to contribute; admitting
    one would place a spurious event at 00:00:00 next to real ones. This is
    why `edit_intensity` and this function treat a 3-record midnight stamp
    differently: counting edits and measuring pace are different questions,
    and only the second needs a real clock time.
    """
    out: list[tuple[str, str]] = []
    for _level, body in schema.iter_v1_descriptions(items):
        na = str(body.get("naId"))
        for t in schema.v1_modifications(body):
            if t.endswith("T00:00:00") or t in machine_stamps:
                continue
            out.append((t, na))
    return out


def sessions_from_events(
    events: list[tuple[str, str]], gap_seconds: int = 300, min_edits: int = 10
) -> list[dict[str, Any]]:
    """Group `(timestamp, naId)` pairs into contiguous activity windows.

    Time-only grouping -- see the warning in `sessions` about what a window
    does and does not tell you.
    """
    from datetime import datetime

    parsed: list[tuple[datetime, str]] = []
    for t, na in events:
        try:
            parsed.append((datetime.fromisoformat(t), na))
        except ValueError:
            continue
    parsed.sort()

    out: list[dict[str, Any]] = []
    cur: list[tuple[datetime, str]] = []
    for ev in parsed:
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


def edit_intensity(
    items: list[dict[str, Any]], exclude_batches: bool = True
) -> dict[str, dict[str, float]]:
    """Mean modifications per record, split by restriction bucket.

    Interpretation (hypothesis, n=3 agencies): elevated edit counts on
    restricted records indicate *individually adjudicated* restriction;
    flat or inverted counts indicate *categorical* restriction applied
    wholesale -- seized foreign records, say, are restricted by category, so
    nothing is reviewed one at a time.

    .. warning::
       The published RG 263 / RG 111 / RG 242 ratios are **stale and not
       reproduced here on purpose.** They were computed before this function
       stopped counting unreviewed records as adjudicated and stopped counting
       batch-import stamps as edits, and both corrections move the numbers by
       unknown amounts -- possibly enough to reverse the RG 242 inversion the
       hypothesis leans on. Recompute from the v1 shards of all three groups
       before citing any figure. `docs/FINDINGS.md` carries the old values
       explicitly marked stale.

    `Restricted - Possibly` gets its own `unreviewed` bucket. The whole
    argument here is about *adjudication* effort, and those records are by
    definition unadjudicated -- folding them into `restricted` can manufacture,
    flatten, or invert the signal depending on how big the backlog is.

    Batch-import timestamps are excluded by default. A single midnight import
    can contribute thousands of modifications whose status composition has
    nothing to do with adjudication -- the 2013-06-27 event alone touched 1,835
    records -- so counting them measures which records happened to be in an
    import, not how much review anyone did. Set `exclude_batches=False` only to
    reproduce a raw count.

    Do not generalize from a single record group.
    """
    noise = batch_timestamps(items) if exclude_batches else set()
    buckets: dict[str, list[int]] = defaultdict(list)
    collect_intensity(items, noise, buckets)
    return intensity_from_buckets(buckets)


def collect_intensity(
    items: list[dict[str, Any]], noise: set[str], buckets: dict[str, list[int]]
) -> None:
    """Fold one shard's per-record edit counts into `buckets`, in place.

    Streaming counterpart to `edit_intensity`: an int per record rather than
    the record. `noise` must be the *group-wide* batch timestamps -- a
    shard-local set misses imports spread thinly across a hash partition.
    """
    for _level, body in schema.iter_v1_descriptions(items):
        r = schema.parse_restriction(body.get("accessRestriction"))
        if r.is_unreviewed:
            key = "unreviewed"
        elif r.is_restricted:
            key = "restricted"
        else:
            key = "open" if r.status else "no_status"
        buckets[key].append(sum(1 for t in schema.v1_modifications(body) if t not in noise))


def intensity_from_buckets(buckets: dict[str, list[int]]) -> dict[str, dict[str, float]]:
    return {
        k: {
            "n": len(v),
            "mean_mods": round(sum(v) / len(v), 3) if v else 0.0,
            "never_edited_pct": round(100 * sum(1 for x in v if x == 0) / len(v), 1) if v else 0.0,
        }
        for k, v in sorted(buckets.items())
    }
