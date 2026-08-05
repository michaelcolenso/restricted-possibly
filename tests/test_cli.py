"""CLI guard tests. No network required -- corpus access is stubbed."""

from __future__ import annotations

import json

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
    """A 3-shard smoke test and an expensive full survey must not collide.

    The group needs more than 3 shards for `--limit-shards 3` to be a real
    sample -- at or above the shard count it is a complete pass and is
    recorded as one.
    """
    monkeypatch.setattr(
        corpus, "shards", lambda *a, **k: [corpus.Shard(f"k{i}", 1) for i in range(5)]
    )
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


def test_a_full_size_limit_is_recorded_as_a_complete_pass(monkeypatch, tmp_path):
    """`--limit-shards 3` on a 3-shard group reads everything.

    Calling that a sample is as wrong as calling a real sample complete: the
    counts are a full survey, and a `.partial` name would file them beside a
    stale full run while the summary implied something was left out.
    """
    monkeypatch.setattr(
        corpus, "shards", lambda *a, **k: [corpus.Shard(f"k{i}", 1) for i in range(3)]
    )
    monkeypatch.setattr(inventory, "build", lambda *a, **k: ([], _summary()))

    result = runner.invoke(
        cli.app, ["inventory", "rg_263", "--out", str(tmp_path), "--limit-shards", "3"]
    )
    assert result.exit_code == 0

    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["summary_rg_263.json", "withheld_rg_263.csv"]
    assert json.loads((tmp_path / "summary_rg_263.json").read_text())["limit_shards"] is None


def test_a_real_sample_is_still_recorded_as_partial(monkeypatch, tmp_path):
    monkeypatch.setattr(
        corpus, "shards", lambda *a, **k: [corpus.Shard(f"k{i}", 1) for i in range(3)]
    )
    monkeypatch.setattr(inventory, "build", lambda *a, **k: ([], _summary()))

    result = runner.invoke(
        cli.app, ["inventory", "rg_263", "--out", str(tmp_path), "--limit-shards", "2"]
    )
    assert result.exit_code == 0

    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == ["summary_rg_263.partial-2shards.json", "withheld_rg_263.partial-2shards.csv"]
    summary = json.loads((tmp_path / "summary_rg_263.partial-2shards.json").read_text())
    assert summary["limit_shards"] == 2


def test_a_nearly_complete_sample_is_still_guarded(monkeypatch):
    """399 of RG 64's 400 shards is ~180 GB, and `samples` is true for it."""
    big = [corpus.Shard(f"k{i}", 500_000_000) for i in range(400)]
    monkeypatch.setattr(corpus, "shards", lambda *a, **k: big)
    called = False

    def _build(*a, **k):
        nonlocal called
        called = True
        return [], _summary()

    monkeypatch.setattr(inventory, "build", _build)

    blocked = runner.invoke(cli.app, ["inventory", "rg_64", "--limit-shards", "399"])
    assert blocked.exit_code == 1
    assert not called


def test_a_small_sample_of_a_large_group_is_allowed(monkeypatch, tmp_path):
    """The guard is on selected bytes, so a genuine smoke test still runs."""
    big = [corpus.Shard(f"k{i}", 500_000_000) for i in range(400)]
    monkeypatch.setattr(corpus, "shards", lambda *a, **k: big)
    monkeypatch.setattr(inventory, "build", lambda *a, **k: ([], _summary()))

    ok = runner.invoke(
        cli.app, ["inventory", "rg_64", "--out", str(tmp_path), "--limit-shards", "3"]
    )
    assert ok.exit_code == 0
