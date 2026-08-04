"""Command-line interface."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import corpus, forensics, inventory, schema

app = typer.Typer(
    add_completion=False,
    help="Survey the National Archives Catalog corpus. Read-only, no credentials.",
)
console = Console()

#: Above this, a full pass is a long uninterruptible commitment. RG 64 is
#: 180 GB and RG 29 is 97 GB; AGENTS.md 4.2 says not to attempt those
#: interactively, and nothing here checkpoints yet.
LARGE_GROUP_GB = 20.0


@app.command()
def groups(
    vintage: str = typer.Option("current", help="current | 2021-12-06 | 2022-04-20 | 2022-12-21"),
    sizes: bool = typer.Option(False, help="Fetch byte totals (slow; one listing per group)."),
    top: int = typer.Option(30, help="With --sizes, show only the N largest."),
) -> None:
    """List record groups. Shard count is a hash partition -- use bytes to size."""
    gs = corpus.list_record_groups(vintage)
    console.print(f"[bold]{len(gs)}[/bold] record groups in vintage [cyan]{vintage}[/cyan]")
    if not sizes:
        console.print(", ".join(gs))
        return
    sized = sorted(((g, corpus.group_bytes(g, vintage)) for g in gs), key=lambda x: -x[1])
    t = Table("record group", "GB")
    for g, b in sized[:top]:
        t.add_row(g, f"{b / 1e9:.2f}")
    console.print(t)


@app.command()
def peek(group: str) -> None:
    """Range-get one record from a group and print its schema keys."""
    sh = corpus.shards(group)
    if not sh:
        console.print(f"[red]no shards for {group}[/red]")
        raise typer.Exit(1)
    rec = corpus.peek(sh[0].key)
    if rec is None:
        console.print("[yellow]first record exceeds range window -- itself a signal[/yellow]")
        raise typer.Exit(1)
    body = rec.get("record", rec)
    console.print(f"[bold]{corpus.resolve_title(body) or group}[/bold]")
    console.print(f"shards: {len(sh)}  bytes: {sum(s.size for s in sh) / 1e9:.2f} GB")
    console.print(f"keys: {sorted(body.keys())}")


@app.command("inventory")
def inventory_cmd(
    group: str,
    out: Path = typer.Option(Path("data"), help="Output directory."),
    limit_shards: int = typer.Option(0, help="0 = all shards. Use a small N to smoke-test."),
    include_personal: bool = typer.Option(
        False,
        help="Emit identifying fields for item/fileUnit (b)(6) records. Off by default.",
    ),
    allow_large: bool = typer.Option(
        False,
        help=f"Permit a group larger than {LARGE_GROUP_GB} GB. There is no checkpointing.",
    ),
) -> None:
    """Extract every withheld description in a record group to CSV."""
    sh = corpus.shards(group)
    if not sh:
        console.print(
            f"[red]no shards for {group} -- nothing was scanned.[/red] A misspelled group "
            "would otherwise produce an empty CSV and a 0% rate that looks like a result."
        )
        raise typer.Exit(1)

    # This scan is not resumable: it writes nothing until the last shard, so an
    # interruption 170 GB into RG 64 costs the whole run. Until checkpointing
    # exists, refuse the groups where that bill is unaffordable rather than
    # letting someone discover it at the end.
    # `--limit-shards N` only counts as a sample if it actually samples:
    # `shards(group)[:N]` with N >= len(sh) is the whole group, and would slip
    # a full 180 GB pass past this guard while labelling the output partial.
    gb = sum(s.size for s in sh) / 1e9
    samples = 0 < limit_shards < len(sh)
    if gb > LARGE_GROUP_GB and not (samples or allow_large):
        console.print(
            f"[red]{group} is {gb:.1f} GB across {len(sh)} shards and this scan has no "
            f"checkpointing[/red] -- an interruption at any point loses everything. "
            "Smoke-test with --limit-shards first, or pass --allow-large to accept the risk."
        )
        raise typer.Exit(1)

    rows, summary = inventory.build(
        group, limit_shards or None, redact_personal=not include_personal
    )

    # A partial run never overwrites a full one: an expensive complete inventory
    # and a 3-shard smoke test are indistinguishable once written, so the limit
    # goes in the filename.
    suffix = f".partial-{limit_shards}shards" if limit_shards else ""
    path = inventory.write_csv(rows, out / f"withheld_{group}{suffix}.csv")
    if limit_shards:
        console.print(
            f"[yellow]partial run: {limit_shards} shards only. These counts are a sample, "
            "not a survey.[/yellow]"
        )

    t = Table("metric", "value")
    t.add_row("scanned", f"{summary.scanned:,}")
    t.add_row("restricted (adjudicated)", f"{summary.restricted:,}")
    t.add_row("unrestricted (denominator)", f"{summary.unrestricted:,}")
    t.add_row("never reviewed (excluded)", f"{summary.unreviewed:,}")
    t.add_row("status absent (legacy imports)", f"{summary.no_status:,}")
    t.add_row("restricted rate", f"{summary.restricted_rate:.2%}")
    console.print(t)

    if include_personal:
        console.print(
            "[yellow]--include-personal: identifying fields for item/fileUnit (b)(6) "
            "records are in this output. Aggregate patterns about agencies are the "
            "product; profiles of named private individuals are not.[/yellow]"
        )
    elif summary.personal_redacted:
        console.print(
            f"[cyan]{summary.personal_redacted:,} (b)(6) rows redacted to aggregate. "
            "They are still counted in every figure above.[/cyan]"
        )

    if summary.parse_failures:
        console.print(
            f"[red]{summary.parse_failures:,} lines failed to parse and are absent from "
            "every count above. Treat these figures as lower bounds and say so if you "
            "publish them.[/red]"
        )

    if summary.by_exemption:
        e = Table("exemption", "n")
        for k, v in summary.by_exemption.items():
            e.add_row(k, str(v))
        console.print(e)
        if "Other" in summary.by_exemption:
            console.print(
                "[yellow]`Other` present -- read the `note` column. It is an escape "
                "hatch from the controlled vocabulary and carries no meaning of its "
                "own; only the note says what the basis actually is, and it is not "
                "always a statute.[/yellow]"
            )
    console.print(f"wrote [green]{path}[/green] ({len(rows)} rows)")
    (out / f"summary_{group}{suffix}.json").write_text(
        json.dumps({**summary.__dict__, "limit_shards": limit_shards or None}, indent=2)
    )


@app.command()
def sessions(shard: list[Path]) -> None:
    """Reconstruct activity windows of hand-paced editing from local v1 shards.

    v1 only -- `recordHistory` does not exist in current data. A window is not
    a person: v1 has no actor field, so concurrent editors merge. See
    `forensics.sessions`.

    Pass **every** shard of the record group. Burst classification is a
    frequency test, and frequencies are only meaningful group-wide: an import
    of 1,835 records spread over 400 shards is ~5 per file, which clears no
    threshold anywhere and gets counted as human activity in each one.

    Two streaming passes, never more than one shard resident. Holding all of
    them at once would need the group's entire deserialized JSON in memory,
    and expanded Python objects run several times the 50 MB+ on-disk size --
    so the fold is over compact per-shard aggregates (a timestamp Counter,
    then `(timestamp, naId)` pairs and per-record edit counts) rather than
    over records.
    """
    if len(shard) == 1:
        console.print(
            "[yellow]single shard: burst counts are shard-local. A group-wide batch "
            "import can fall below threshold here and be misread as human activity.[/yellow]"
        )

    # Pass 1: group-wide timestamp frequencies. Nothing can be classified
    # before this exists, which is why one pass will not do.
    counts: Counter[str] = Counter()
    for path in shard:
        counts += forensics.timestamp_counts(schema.load_v1(path))

    machine = forensics.tool_timestamps_from_counts(counts)
    noise = forensics.batch_timestamps_from_counts(counts)

    # Pass 2: fold the compact per-shard aggregates.
    events: list[tuple[str, str]] = []
    buckets: dict[str, list[int]] = defaultdict(list)
    for path in shard:
        items = schema.load_v1(path)
        events += forensics.collect_events(items, machine)
        forensics.collect_intensity(items, noise, buckets)

    console.print(f"{sum(counts.values()):,} modifications across {len(shard)} shard(s)")

    t = Table("timestamp", "records", "classification")
    for burst in forensics.bursts_from_counts(counts)[:8]:
        t.add_row(burst.timestamp, str(burst.count), burst.classification)
    console.print(t)

    for s in forensics.sessions_from_events(events):
        console.print(
            f"[bold]{s['start']}[/bold] -> {s['end']}  "
            f"{s['count']} edits over {s['duration_minutes']} min "
            f"(mean {s['mean_interval_seconds']}s apart)"
        )

    console.print(forensics.intensity_from_buckets(buckets))


def main() -> None:
    app()
