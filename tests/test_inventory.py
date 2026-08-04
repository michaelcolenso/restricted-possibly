"""Inventory logic tests. No network required."""

from __future__ import annotations

from restricted_possibly import corpus, inventory


def _rec(na: str, status: str | None) -> dict:
    access = {"status": status, "specificAccessRestrictions": []} if status else None
    return {
        "naId": na,
        "levelOfDescription": "fileUnit",
        "title": f"record {na}",
        "accessRestriction": access,
        "ancestors": [{"levelOfDescription": "recordGroup", "recordGroupNumber": 263}],
    }


def test_build_excludes_unreviewed_from_withheld_rows(monkeypatch):
    """`Restricted - Possibly` is a processing backlog, not a withholding.

    It belongs in `unreviewed` and in `by_status`, and nowhere near the
    numerator or denominator of the rate.
    """
    records = [
        _rec("1", "Restricted - Fully"),
        _rec("2", "Restricted - Partly"),
        _rec("3", "Restricted - Possibly"),
        _rec("4", "Restricted - Possibly"),
        _rec("5", "Unrestricted"),
        _rec("6", "Unrestricted"),
        _rec("7", None),
    ]
    monkeypatch.setattr(corpus, "stream_group", lambda *a, **k: iter(records))

    rows, s = inventory.build("rg_test")

    assert [r.naId for r in rows] == ["1", "2"]
    assert (s.restricted, s.unrestricted, s.unreviewed, s.no_status) == (2, 2, 2, 1)
    assert s.by_status["Restricted - Possibly"] == 2  # still reported
    assert s.restricted_rate == 0.5  # 2 / (2 + 2), backlog excluded from both


def test_write_once_detects_stability():
    """Established for RG 263: status does not mutate across four years."""
    old = {"1": "Restricted - Fully", "2": "Restricted - Partly"}
    cur = {"1": "Restricted - Fully", "2": "Restricted - Partly"}
    out = inventory.write_once_check(old, cur)
    assert out == {
        "Restricted - Fully -> Restricted - Fully": 1,
        "Restricted - Partly -> Restricted - Partly": 1,
    }


def test_write_once_would_flag_a_declassification():
    """A counterexample in another record group would be a significant finding."""
    out = inventory.write_once_check({"1": "Restricted - Fully"}, {"1": "Unrestricted"})
    assert out == {"Restricted - Fully -> Unrestricted": 1}


def test_restricted_rate_excludes_unreviewed_and_absent():
    s = inventory.Summary(
        group="rg_test",
        scanned=1000,
        restricted=70,
        unrestricted=930,
        unreviewed=500,
        no_status=1885,
        by_status={},
        by_exemption={},
        by_level={},
    )
    # denominator is restricted + unrestricted only
    assert abs(s.restricted_rate - 0.07) < 1e-9


def test_restricted_rate_handles_empty():
    s = inventory.Summary("x", 0, 0, 0, 0, 0, {}, {}, {})
    assert s.restricted_rate == 0.0


def test_row_fields_carry_the_legal_basis():
    """`Other` is meaningless without its note; the classification qualifies it."""
    names = [f.name for f in inventory.Row.__dataclass_fields__.values()]
    assert names == [
        "naId",
        "recordGroup",
        "level",
        "status",
        "exemptions",
        "securityClassification",
        "note",
        "coverageStart",
        "coverageEnd",
        "mediaType",
        "containers",
        "location",
        "title",
    ]


def test_note_is_never_truncated(monkeypatch):
    """The note is the legal basis; a cut-off statute is worse than none."""
    long_note = "Per the CIA Information Act of 1984, " + "x" * 5000
    rec = _rec("1", "Restricted - Fully")
    rec["accessRestriction"] = {
        "status": "Restricted - Fully",
        "specificAccessRestrictions": [],
        "note": long_note,
    }
    monkeypatch.setattr(corpus, "stream_group", lambda *a, **k: iter([rec]))

    (row,), _ = inventory.build("rg_test")
    assert row.note == long_note


def test_build_reports_parse_failures(monkeypatch):
    """A skipped line shrinks the denominator; the count has to surface."""

    def fake_stream(group, prefilter=None, limit_shards=None, stats=None):
        if stats is not None:
            stats.parse_failures += 3
            stats.parsed += 1
        return iter([_rec("1", "Restricted - Fully")])

    monkeypatch.setattr(corpus, "stream_group", fake_stream)

    _, s = inventory.build("rg_test")
    assert s.parse_failures == 3
    assert s.scanned == 1  # unparsable lines never reach `scanned`


def test_csv_roundtrip(tmp_path):
    rows = [
        inventory.Row(
            naId="5956115",
            recordGroup=263,
            level="series",
            status="Restricted - Fully",
            exemptions="Other",
            securityClassification="Top Secret",
            coverageStart=None,
            coverageEnd=None,
            mediaType="Textual Records",
            containers="Box 1",
            location="National Archives at College Park",
            title="Headquarters PBFORTUNE/PBSUCCESS Planning Files",
            note="Per the CIA Information Act of 1984...",
        )
    ]
    p = inventory.write_csv(rows, tmp_path / "out.csv")
    text = p.read_text()
    assert "note" in text.splitlines()[0]  # note column present
    assert "1984" in text  # and populated


def _personal(na: str, level: str, exemptions: list[str]) -> dict:
    rec = _rec(na, "Restricted - Partly")
    rec["levelOfDescription"] = level
    rec["accessRestriction"] = {
        "status": "Restricted - Partly",
        "specificAccessRestrictions": [{"restriction": e} for e in exemptions],
        "note": "Contains personal information about the subject.",
    }
    rec["physicalOccurrences"] = [
        {
            "mediaOccurrences": [{"specificMediaType": "Textual Records", "containerId": "Box 9"}],
            "referenceUnits": [{"name": "National Archives at St. Louis"}],
        }
    ]
    return rec


def test_item_level_b6_records_are_redacted_to_aggregate(monkeypatch):
    """Run over RG 15 or RG 85, row-level (b)(6) is a person-level dossier."""
    records = [_personal("1", "fileUnit", [inventory.PERSONAL])]
    monkeypatch.setattr(corpus, "stream_group", lambda *a, **k: iter(records))

    (row,), s = inventory.build("rg_15")

    assert s.personal_redacted == 1
    assert s.restricted == 1  # still counted
    assert row.exemptions == inventory.PERSONAL  # still classifiable
    assert row.title == row.note == row.containers == row.location == inventory.REDACTED
    assert row.naId == "1"


def test_series_level_b6_records_are_left_intact(monkeypatch):
    """A series carrying (b)(6) describes a body of records, not a person."""
    records = [_personal("2", "series", [inventory.PERSONAL])]
    monkeypatch.setattr(corpus, "stream_group", lambda *a, **k: iter(records))

    (row,), s = inventory.build("rg_263")

    assert s.personal_redacted == 0
    assert row.title == "record 2"
    assert row.location == "National Archives at St. Louis"


def test_redaction_can_be_turned_off_deliberately(monkeypatch):
    records = [_personal("3", "item", [inventory.PERSONAL])]
    monkeypatch.setattr(corpus, "stream_group", lambda *a, **k: iter(records))

    (row,), s = inventory.build("rg_15", redact_personal=False)

    assert s.personal_redacted == 0
    assert row.title == "record 3"
