"""Live bucket tests. Deselect with: pytest -m 'not network'"""

from __future__ import annotations

import pytest

from restricted_possibly import corpus

pytestmark = pytest.mark.network


def test_bucket_is_publicly_readable():
    groups = corpus.list_record_groups()
    assert len(groups) > 500
    assert "rg_263" in groups


def test_collections_exist():
    assert len(corpus.list_collections()) > 5000


def test_peek_returns_a_record():
    rec = corpus.peek(corpus.shards("rg_263")[0].key)
    assert rec is not None
    assert "record" in rec


def test_v2_schema_has_no_record_history():
    """Guards the documented v1-only constraint against silent schema drift."""
    rec = corpus.peek(corpus.shards("rg_263")[0].key)["record"]
    assert "recordHistory" not in rec, "recordHistory reappeared -- forensics now work on v2!"
