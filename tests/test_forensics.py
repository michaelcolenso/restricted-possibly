"""Forensics bucketing tests. No network required."""

from __future__ import annotations

from collections import Counter, defaultdict

from restricted_possibly import forensics


def _shard(*records: tuple[str | None, int]) -> list[dict]:
    """Build a v1-shaped shard: (status, modification_count) per record."""
    items = []
    for i, (status, mods) in enumerate(records):
        access = {"status": status, "specificAccessRestrictions": []} if status else None
        items.append(
            {
                "description": {
                    "fileUnit": {
                        "naId": str(i),
                        "accessRestriction": access,
                        "recordHistory": {
                            "changed": {
                                "modification": [
                                    {"dateTime": f"2018-10-03T09:{m:02d}:00"} for m in range(mods)
                                ]
                            }
                        },
                    }
                }
            }
        )
    return items


def test_edit_intensity_separates_unreviewed_from_adjudicated():
    """The claim is about adjudication effort, so the backlog cannot sit in it.

    Here the unreviewed records are never edited. Folded into `restricted`
    they would drag its mean from 4.0 down to 1.6 and invert the RG 263
    signal outright.
    """
    items = _shard(
        ("Restricted - Fully", 4),
        ("Restricted - Partly", 4),
        ("Restricted - Possibly", 0),
        ("Restricted - Possibly", 0),
        ("Restricted - Possibly", 0),
        ("Unrestricted", 1),
    )
    out = forensics.edit_intensity(items)

    assert out["restricted"] == {"n": 2, "mean_mods": 4.0, "never_edited_pct": 0.0}
    assert out["unreviewed"] == {"n": 3, "mean_mods": 0.0, "never_edited_pct": 100.0}
    assert out["open"]["n"] == 1


def test_edit_intensity_buckets_absent_status_separately():
    """Status-absent records are 2001 migration imports -- their own class."""
    out = forensics.edit_intensity(_shard((None, 0), ("Unrestricted", 2)))
    assert out["no_status"]["n"] == 1
    assert out["open"]["n"] == 1


def test_midnight_bursts_classify_as_machine():
    items = [
        {
            "description": {
                "fileUnit": {
                    "naId": str(i),
                    "recordHistory": {
                        "changed": {"modification": [{"dateTime": "2013-06-27T00:00:00"}]}
                    },
                }
            }
        }
        for i in range(60)
    ]
    (burst,) = forensics.bursts(items)
    assert burst.count == 60
    assert burst.classification == "automated batch import"
    assert forensics.batch_timestamps(items) == {"2013-06-27T00:00:00"}


def _stamped(*records: tuple[str | None, list[str]]) -> list[dict]:
    """Build a v1-shaped shard with explicit modification timestamps."""
    items = []
    for i, (status, stamps) in enumerate(records):
        access = {"status": status, "specificAccessRestrictions": []} if status else None
        items.append(
            {
                "description": {
                    "fileUnit": {
                        "naId": str(i),
                        "accessRestriction": access,
                        "recordHistory": {
                            "changed": {"modification": [{"dateTime": s} for s in stamps]}
                        },
                    }
                }
            }
        )
    return items


def test_edit_intensity_excludes_batch_imports():
    """A midnight import measures what got imported, not what got adjudicated.

    Here every record carries the same batch stamp and only the restricted one
    was ever hand-edited. Counting the import flattens the ratio to 1.0.
    """
    batch = "2013-06-27T00:00:00"
    records: list[tuple[str | None, list[str]]] = [("Unrestricted", [batch]) for _ in range(60)]
    records.append(("Restricted - Fully", [batch, "2018-10-03T09:45:00"]))
    items = _stamped(*records)

    filtered = forensics.edit_intensity(items)
    assert filtered["open"]["mean_mods"] == 0.0
    assert filtered["restricted"]["mean_mods"] == 1.0

    raw = forensics.edit_intensity(items, exclude_batches=False)
    assert raw["open"]["mean_mods"] == 1.0
    assert raw["restricted"]["mean_mods"] == 2.0


def test_sessions_excludes_bulk_tool_bursts():
    """The verified 45-record tool event is not a person working a queue."""
    burst = "2015-11-20T17:18:21"
    tool = [(None, [burst]) for _ in range(45)]
    human = [
        (None, [f"2018-10-03T09:{m:02d}:00"]) for m in range(45, 60)
    ]  # steady 1-minute cadence
    out = forensics.sessions(_stamped(*tool, *human))

    assert len(out) == 1
    (session,) = out
    assert session["count"] == 15
    assert session["start"].startswith("2018-10-03T09:45")
    assert session["mean_interval_seconds"] > 0


def test_streaming_primitives_match_the_single_shard_functions():
    """The two-pass CLI path must agree with the all-in-memory one.

    `rp sessions` folds compact per-shard aggregates instead of concatenating
    every parsed shard, so the aggregates have to reproduce the same answer.
    """
    burst = "2015-11-20T17:18:21"
    batch = "2013-06-27T00:00:00"
    shard_a = _stamped(
        *[("Unrestricted", [batch, burst]) for _ in range(30)],
        ("Restricted - Fully", [batch, "2018-10-03T09:00:00"]),
    )
    shard_b = _stamped(
        *[("Unrestricted", [batch, burst]) for _ in range(30)],
        *[(None, [f"2018-10-03T10:{m:02d}:00"]) for m in range(0, 30, 2)],
    )
    whole = shard_a + shard_b

    counts: Counter[str] = Counter()
    for shard in (shard_a, shard_b):
        counts += forensics.timestamp_counts(shard)
    machine = {t for t, n in counts.items() if n > 5}
    noise = forensics.batch_timestamps_from_counts(counts)

    events: list[tuple[str, str]] = []
    buckets: dict[str, list[int]] = defaultdict(list)
    for shard in (shard_a, shard_b):
        events += forensics.collect_events(shard, machine)
        forensics.collect_intensity(shard, noise, buckets)

    assert forensics.sessions_from_events(events) == forensics.sessions(whole)
    assert forensics.intensity_from_buckets(buckets) == forensics.edit_intensity(whole)
    assert forensics.bursts_from_counts(counts) == forensics.bursts(whole)


def test_group_wide_counts_catch_a_batch_that_hides_in_every_shard():
    """The reason pass 1 exists: 60 records over 30 shards is 2 per file."""
    shards = [
        _stamped(
            ("Unrestricted", ["2013-06-27T00:00:00"]), ("Unrestricted", ["2013-06-27T00:00:00"])
        )
        for _ in range(30)
    ]

    per_shard = [forensics.batch_timestamps(s) for s in shards]
    assert all(s == set() for s in per_shard)  # invisible shard-by-shard

    counts: Counter[str] = Counter()
    for s in shards:
        counts += forensics.timestamp_counts(s)
    assert forensics.batch_timestamps_from_counts(counts) == {"2013-06-27T00:00:00"}


def test_batch_boundary_is_the_same_for_filtering_and_labelling():
    """At exactly 50, the filter dropped the event and the label kept it."""
    stamp = "2013-06-27T00:00:00"
    counts = Counter({stamp: forensics.BATCH_THRESHOLD})

    (burst,) = forensics.bursts_from_counts(counts)
    assert burst.classification == "automated batch import"
    assert forensics.batch_timestamps_from_counts(counts) == {stamp}

    below = Counter({stamp: forensics.BATCH_THRESHOLD - 1})
    (burst,) = forensics.bursts_from_counts(below)
    assert burst.classification != "automated batch import"
    assert forensics.batch_timestamps_from_counts(below) == set()


def test_tool_boundary_is_the_same_for_labelling_and_session_exclusion():
    stamp = "2015-11-20T17:18:21"
    at = Counter({stamp: forensics.TOOL_THRESHOLD})
    (burst,) = forensics.bursts_from_counts(at)
    assert burst.classification == "interactive bulk tool"

    items = _stamped(*[(None, [stamp]) for _ in range(forensics.TOOL_THRESHOLD)])
    assert forensics.sessions(items, min_edits=1) == []  # excluded, not a person
