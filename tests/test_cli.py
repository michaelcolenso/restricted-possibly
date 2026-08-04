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


def test_inventory_refuses_a_group_too_large_to_run_without_checkpointing(monkeypatch):
    """RG 64 is 180 GB and this scan writes nothing until the last shard."""
    big = [corpus.Shard(f"k{i}", 500_000_000) for i in range(400)]  # 200 GB
    monkeypatch.setattr(corpus, "shards", lambda *a, **k: big)
    called = False

    def _build(*a, **k):
        nonlocal called
        called = True
        return [], _summary()

    monkeypatch.setattr(inventory, "build", _build)

    blocked = runner.invoke(cli.app, ["inventory", "rg_64"])
    assert blocked.exit_code == 1
    assert not called


def test_large_group_is_allowed_deliberately_or_when_sampled(monkeypatch, tmp_path):
    big = [corpus.Shard(f"k{i}", 500_000_000) for i in range(400)]
    monkeypatch.setattr(corpus, "shards", lambda *a, **k: big)
    monkeypatch.setattr(inventory, "build", lambda *a, **k: ([], _summary()))

    forced = runner.invoke(cli.app, ["inventory", "rg_64", "--out", str(tmp_path), "--allow-large"])
    assert forced.exit_code == 0

    sampled = runner.invoke(
        cli.app, ["inventory", "rg_64", "--out", str(tmp_path), "--limit-shards", "2"]
    )
    assert sampled.exit_code == 0


def test_limit_shards_at_or_above_the_shard_count_does_not_bypass_the_guard(monkeypatch):
    """`shards(group)[:400]` on a 400-shard group is the whole 180 GB of it."""
    big = [corpus.Shard(f"k{i}", 500_000_000) for i in range(400)]
    monkeypatch.setattr(corpus, "shards", lambda *a, **k: big)
    monkeypatch.setattr(inventory, "build", lambda *a, **k: ([], _summary()))

    for limit in ("400", "500"):
        result = runner.invoke(cli.app, ["inventory", "rg_64", "--limit-shards", limit])
        assert result.exit_code == 1, f"--limit-shards {limit} slipped past the guard"


def test_negative_shard_limits_are_rejected(monkeypatch):
    """`shards(group)[:-1]` scans all but the last shard, labelled "-1 shards"."""
    monkeypatch.setattr(corpus, "shards", lambda *a, **k: [corpus.Shard("k", 1)])
    called = False

    def _build(*a, **k):
        nonlocal called
        called = True
        return [], _summary()

    monkeypatch.setattr(inventory, "build", _build)

    result = runner.invoke(cli.app, ["inventory", "rg_263", "--limit-shards", "-1"])
    assert result.exit_code != 0
    assert not called
