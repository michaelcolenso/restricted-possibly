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
        "title",
    ]


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
            title="Headquarters PBFORTUNE/PBSUCCESS Planning Files",
            note="Per the CIA Information Act of 1984...",
        )
    ]
    p = inventory.write_csv(rows, tmp_path / "out.csv")
    text = p.read_text()
    assert "note" in text.splitlines()[0]  # note column present
    assert "1984" in text  # and populated
