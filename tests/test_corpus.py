"""Corpus parsing tests. No network required -- the S3 client is stubbed."""

from __future__ import annotations

import io
import json

from restricted_possibly import corpus


def _stream(lines: list[str], monkeypatch) -> tuple[list[dict], corpus.ScanStats]:
    class _Client:
        def get_object(self, **kw):
            return {"Body": io.BytesIO("\n".join(lines).encode())}

    monkeypatch.setattr(corpus, "client", lambda: _Client())
    stats = corpus.ScanStats()
    return list(corpus.stream_shard("k", stats=stats)), stats


def test_valid_json_of_the_wrong_shape_counts_as_a_parse_failure(monkeypatch):
    """A line can be valid JSON and still not be a record.

    A bare array used to raise TypeError and abort the whole 400-shard pass;
    `{"record": null}` used to be counted as parsed and yield None, which then
    failed downstream while sitting inside the denominator.
    """
    records, stats = _stream(
        [
            json.dumps({"record": {"naId": 1}}),  # good
            "[{}]",  # root array -- used to raise TypeError
            json.dumps({"record": None}),  # used to yield None as a "record"
            json.dumps({"record": "not a dict"}),
            json.dumps({"naId": 2}),  # no wrapper
            "{not json",  # not JSON at all
            json.dumps({"record": {"naId": 3}}),  # good
        ],
        monkeypatch,
    )

    assert [r["naId"] for r in records] == [1, 3]
    assert stats.parsed == 2
    assert stats.parse_failures == 5
    assert abs(stats.failure_rate - 5 / 7) < 1e-9


def test_prefiltered_lines_are_not_parse_failures(monkeypatch):
    """A line rejected by the substring prefilter was never a candidate."""

    class _Client:
        def get_object(self, **kw):
            body = "\n".join(
                [
                    json.dumps({"record": {"naId": 1, "accessRestriction": "Restricted"}}),
                    json.dumps({"record": {"naId": 2}}),
                    "",
                ]
            )
            return {"Body": io.BytesIO(body.encode())}

    monkeypatch.setattr(corpus, "client", lambda: _Client())
    stats = corpus.ScanStats()
    records = list(corpus.stream_shard("k", prefilter='"Restricted', stats=stats))

    assert [r["naId"] for r in records] == [1]
    assert stats.parse_failures == 0
