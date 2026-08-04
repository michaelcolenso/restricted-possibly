"""Forensics bucketing tests. No network required."""

from __future__ import annotations

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
