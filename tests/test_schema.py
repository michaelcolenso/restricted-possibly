"""Schema normalization tests. No network required."""

from __future__ import annotations

import json

import pytest

from restricted_possibly import forensics, schema

# --- v1 fixture: malformed wrapper, nested, termName-encoded ---------------
V1_RAW = """{[{"type":"description","naId":"46292","description":{"series":{
"naId":"46292",
"title":"Test Series",
"accessRestriction":{"status":{"naId":"10031403","termName":"Restricted - Fully"},
 "specificAccessRestrictionArray":{"specificAccessRestriction":{
   "restriction":{"naId":"1","termName":"FOIA (b)(1) National Security"},
   "securityClassification":{"naId":"2","termName":"Top Secret"}}},
 "note":"Per the CIA Information Act of 1984..."},
"recordHistory":{"created":{"dateTime":"2001-11-30T00:00:00"},
 "changed":{"modification":[{"dateTime":"2013-06-27T00:00:00"},
                            {"dateTime":"2018-10-03T09:45:21"}]}}}}}]}"""

# --- v2 fixture: JSONL, flat, bare strings ---------------------------------
V2_LINE = json.dumps(
    {
        "record": {
            "naId": 5956115,
            "title": "Headquarters PBFORTUNE/PBSUCCESS Planning Files",
            "levelOfDescription": "series",
            "accessRestriction": {
                "status": "Restricted - Fully",
                "specificAccessRestrictions": [
                    {"restriction": "Other", "securityClassification": "Top Secret"}
                ],
                "note": "Per the CIA Information Act of 1984...",
            },
            "coverageStartDate": {"year": 1952, "logicalDate": "1952-01-01"},
        }
    }
)


def test_v1_wrapper_is_repaired(tmp_path):
    p = tmp_path / "v1.json"
    p.write_text(V1_RAW)
    items = schema.load_v1(p)
    assert len(items) == 1
    assert items[0]["naId"] == "46292"


def test_v1_and_v2_restrictions_normalize_identically(tmp_path):
    p = tmp_path / "v1.json"
    p.write_text(V1_RAW)
    v1_body = next(schema.iter_v1_descriptions(schema.load_v1(p)))[1]
    r1 = schema.parse_restriction(v1_body["accessRestriction"])

    v2 = json.loads(V2_LINE)["record"]
    r2 = schema.parse_restriction(v2["accessRestriction"])

    # Same status despite completely different encodings.
    assert r1.status == r2.status == "Restricted - Fully"
    assert r1.security_classification == r2.security_classification == "Top Secret"
    assert r1.is_restricted and r2.is_restricted
    # termName unwrapping
    assert r1.exemptions == ["FOIA (b)(1) National Security"]
    assert r2.exemptions == ["Other"]


def test_note_is_captured():
    """Regression: the original script dropped `note`, making `Other` unexplainable."""
    r = schema.parse_restriction(json.loads(V2_LINE)["record"]["accessRestriction"])
    assert r.note is not None and "1984" in r.note


def test_unreviewed_is_not_conflated_with_withheld():
    r = schema.parse_restriction({"status": "Restricted - Possibly"})
    assert r.is_restricted  # it is in the restricted vocabulary...
    assert r.is_unreviewed  # ...but it means "not yet looked at"


def test_absent_restriction_is_empty():
    r = schema.parse_restriction(None)
    assert r.status is None and not r.is_restricted and r.exemptions == []


def test_year_extraction():
    assert schema.year({"year": 1952}) == 1952
    assert schema.year(None) is None


def test_v1_modifications_and_created(tmp_path):
    p = tmp_path / "v1.json"
    p.write_text(V1_RAW)
    body = next(schema.iter_v1_descriptions(schema.load_v1(p)))[1]
    assert schema.v1_created(body) == "2001-11-30T00:00:00"
    assert len(schema.v1_modifications(body)) == 2


def test_v2_records_have_no_edit_history():
    """recordHistory was dropped in v2. Guards against rebuilding forensics on it."""
    v2 = json.loads(V2_LINE)["record"]
    assert "recordHistory" not in v2
    assert schema.v1_modifications(v2) == []


# --- forensics -------------------------------------------------------------


@pytest.mark.parametrize(
    ("stamp", "count", "expected"),
    [
        ("2013-06-27T00:00:00", 1835, "automated batch import"),
        ("2015-11-20T17:18:21", 45, "interactive bulk tool"),
        ("2018-10-03T09:45:21", 1, "manual edit"),
    ],
)
def test_burst_classification(stamp, count, expected):
    assert forensics.Burst(stamp, count).classification == expected


def test_midnight_detection():
    assert forensics.Burst("2013-06-27T00:00:00", 10).is_midnight
    assert not forensics.Burst("2018-10-03T09:45:21", 10).is_midnight
