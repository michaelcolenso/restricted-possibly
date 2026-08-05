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
    limit_shards: int = typer.Option(0, min=0, help="0 = all shards. Use a small N to smoke-test."),
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
    # exists, refuse the reads where that bill is unaffordable rather than
    # letting someone discover it at the end.
    #
    # The guard is on *bytes actually selected*, not on whether a limit was
    # given. `--limit-shards N` with N >= len(sh) is the whole group, and even
    # a strict subset can be nearly all of it -- 399 of RG 64's 400 shards is
    # ~180 GB and would have slipped through a shard-count test.
    samples = 0 < limit_shards < len(sh)
    selected = sh[:limit_shards] if samples else sh
    gb = sum(s.size for s in selected) / 1e9
    if gb > LARGE_GROUP_GB and not allow_large:
        scope = f"{len(selected)} of {len(sh)} shards" if samples else f"all {len(sh)} shards"
        console.print(
            f"[red]{group}: {scope} is {gb:.1f} GB and this scan has no checkpointing"
            f"[/red] -- an interruption at any point loses everything. Use a smaller "
            "--limit-shards, or pass --allow-large to accept the risk."
        )
        raise typer.Exit(1)

    rows, summary = inventory.build(
        group, limit_shards or None, redact_personal=not include_personal
    )

    # `samples` -- not `limit_shards` -- decides whether this run is partial.
    # `--limit-shards 400` on a 400-shard group reads every record, so calling
    # it a sample would be as wrong as calling a real sample complete: the
    # counts are a full survey, they would be filed under a `.partial` name
    # beside a stale full run, and the summary would carry a limit implying
    # something was left out.
    suffix = f".partial-{limit_shards}shards" if samples else ""
    path = inventory.write_csv(rows, out / f"withheld_{group}{suffix}.csv")
    if samples:
        console.print(
            f"[yellow]partial run: {limit_shards} of {len(sh)} shards. These counts are "
            "a sample, not a survey.[/yellow]"
        )
    elif limit_shards:
        console.print(
            f"[cyan]--limit-shards {limit_shards} covers all {len(sh)} shards: this is a "
            "complete pass, recorded as one.[/cyan]"
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
        json.dumps(
            {**summary.__dict__, "limit_shards": limit_shards if samples else None}, indent=2
        )
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
