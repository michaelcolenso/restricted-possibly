"""Command-line interface."""

from __future__ import annotations

import json
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
) -> None:
    """Extract every withheld description in a record group to CSV."""
    rows, summary = inventory.build(group, limit_shards or None)
    path = inventory.write_csv(rows, out / f"withheld_{group}.csv")

    t = Table("metric", "value")
    t.add_row("scanned", f"{summary.scanned:,}")
    t.add_row("restricted (adjudicated)", f"{summary.restricted:,}")
    t.add_row("unrestricted (denominator)", f"{summary.unrestricted:,}")
    t.add_row("never reviewed (excluded)", f"{summary.unreviewed:,}")
    t.add_row("status absent (legacy imports)", f"{summary.no_status:,}")
    t.add_row("restricted rate", f"{summary.restricted_rate:.2%}")
    console.print(t)

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
                "[yellow]`Other` present -- read the `note` column. "
                "It is an escape hatch from the controlled vocabulary and the "
                "note carries the actual statute.[/yellow]"
            )
    console.print(f"wrote [green]{path}[/green] ({len(rows)} rows)")
    (out / f"summary_{group}.json").write_text(json.dumps(summary.__dict__, indent=2))


@app.command()
def sessions(shard: Path) -> None:
    """Reconstruct human working sessions from a local v1 shard.

    v1 only -- `recordHistory` does not exist in current data.
    """
    items = schema.load_v1(shard)
    console.print(f"parsed {len(items):,} items")

    b = forensics.bursts(items)[:8]
    t = Table("timestamp", "records", "classification")
    for burst in b:
        t.add_row(burst.timestamp, str(burst.count), burst.classification)
    console.print(t)

    for s in forensics.sessions(items):
        console.print(
            f"[bold]{s['start']}[/bold] -> {s['end']}  "
            f"{s['count']} edits over {s['duration_minutes']} min "
            f"(mean {s['mean_interval_seconds']}s apart)"
        )

    console.print(forensics.edit_intensity(items))


def main() -> None:
    app()
