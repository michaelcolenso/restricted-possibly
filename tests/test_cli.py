"""CLI guard tests. No network required -- corpus access is stubbed."""

from __future__ import annotations

from typer.testing import CliRunner

from restricted_possibly import cli, corpus, inventory

runner = CliRunner()


def _summary(**kw):
    defaults = {
        "group": "rg_test",
        "scanned": 10,
        "restricted": 1,
        "unrestricted": 9,
        "unreviewed": 0,
        "no_status": 0,
        "by_status": {},
        "by_exemption": {},
        "by_level": {},
    }
    return inventory.Summary(**{**defaults, **kw})


def test_inventory_refuses_a_group_with_no_shards(monkeypatch):
    """A misspelled group must not produce an empty CSV and a 0% rate."""
    monkeypatch.setattr(corpus, "shards", lambda *a, **k: [])
    called = False

    def _build(*a, **k):
        nonlocal called
        called = True
        return [], _summary()

    monkeypatch.setattr(inventory, "build", _build)

    result = runner.invoke(cli.app, ["inventory", "rg_typo"])
    assert result.exit_code == 1
    assert not called  # bailed before scanning


def test_partial_run_does_not_overwrite_a_full_inventory(monkeypatch, tmp_path):
    """A 3-shard smoke test and an expensive full survey must not collide."""
    monkeypatch.setattr(corpus, "shards", lambda *a, **k: [corpus.Shard("k", 1)])
    monkeypatch.setattr(inventory, "build", lambda *a, **k: ([], _summary()))

    full = runner.invoke(cli.app, ["inventory", "rg_263", "--out", str(tmp_path)])
    assert full.exit_code == 0

    partial = runner.invoke(
        cli.app, ["inventory", "rg_263", "--out", str(tmp_path), "--limit-shards", "3"]
    )
    assert partial.exit_code == 0

    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == [
        "summary_rg_263.json",
        "summary_rg_263.partial-3shards.json",
        "withheld_rg_263.csv",
        "withheld_rg_263.partial-3shards.csv",
    ]
