"""Unauthenticated access to the NARA Catalog corpus on S3.

The bucket is public and requires no AWS account. Every function here is
read-only; nothing in this package can write to NARA infrastructure.
"""

from __future__ import annotations

import io
import json
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import boto3
from botocore import UNSIGNED
from botocore.config import Config

BUCKET = "nara-national-archives-catalog"

#: Historical snapshots. These use the legacy v1 schema (see `schema.py`)
#: and have *partial* record-group coverage -- always check before assuming.
VINTAGES = {
    "2021-12-06": "backups/descriptions20211206",
    "2022-04-20": "backups/descriptions20220420",
    "2022-12-21": "backups/descriptions20221221",
    "current": "descriptions",
}


@lru_cache(maxsize=1)
def client():
    """Anonymous S3 client. Cached; safe to call repeatedly."""
    return boto3.client("s3", config=Config(signature_version=UNSIGNED))


@dataclass(frozen=True)
class Shard:
    key: str
    size: int

    @property
    def is_jsonl(self) -> bool:
        return self.key.endswith(".jsonl")


def list_record_groups(vintage: str = "current") -> list[str]:
    """All record-group directory names (e.g. 'rg_263') in a vintage."""
    return _list_prefixes(f"{VINTAGES[vintage]}/record-groups/")


def list_collections(vintage: str = "current") -> list[str]:
    """All collection directory names (e.g. 'coll_JFK') in a vintage."""
    return _list_prefixes(f"{VINTAGES[vintage]}/collections/")


def _list_prefixes(prefix: str) -> list[str]:
    out: list[str] = []
    for page in (
        client()
        .get_paginator("list_objects_v2")
        .paginate(Bucket=BUCKET, Prefix=prefix, Delimiter="/")
    ):
        out += [p["Prefix"].rstrip("/").split("/")[-1] for p in page.get("CommonPrefixes", [])]
    return sorted(out)


def shards(group: str, vintage: str = "current") -> list[Shard]:
    """Every shard for a record group.

    Note: shard *count* is always ~400 for v2 -- it is a hash partition, not a
    volume signal. Use total bytes to size a group.
    """
    prefix = f"{VINTAGES[vintage]}/record-groups/{group}/"
    out: list[Shard] = []
    for page in client().get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix):
        out += [Shard(o["Key"], o["Size"]) for o in page.get("Contents", []) if o["Size"] > 0]
    return out


def group_bytes(group: str, vintage: str = "current") -> int:
    return sum(s.size for s in shards(group, vintage))


def peek(key: str, nbytes: int = 300_000) -> dict[str, Any] | None:
    """Range-get the head of a shard and parse its first record.

    Cheap reconnaissance -- never download a 50 MB shard to inspect a schema.
    Some single records exceed 1.5 MB; if this returns None, widen `nbytes`.
    An oversized first record is itself a signal worth investigating.
    """
    body = (
        client()
        .get_object(Bucket=BUCKET, Key=key, Range=f"bytes=0-{nbytes}")["Body"]
        .read()
        .decode("utf-8", "replace")
    )
    nl = body.find("\n")
    if nl == -1:
        return None
    try:
        return json.loads(body[:nl])
    except json.JSONDecodeError:
        return None


def stream_shard(key: str, prefilter: str | None = None) -> Iterator[dict[str, Any]]:
    """Stream parsed records from a v2 JSONL shard.

    `prefilter` is a raw substring tested against each line *before* JSON
    parsing. Full scans are bound by parse cost, not network -- rejecting
    lines cheaply is what makes 400-shard passes tractable.
    """
    obj = client().get_object(Bucket=BUCKET, Key=key)
    for line in io.TextIOWrapper(obj["Body"], encoding="utf-8", errors="replace"):
        if not line.strip():
            continue
        if prefilter is not None and prefilter not in line:
            continue
        try:
            yield json.loads(line)["record"]
        except (json.JSONDecodeError, KeyError):
            continue


def stream_group(
    group: str, prefilter: str | None = None, limit_shards: int | None = None
) -> Iterator[dict[str, Any]]:
    """Stream every record in a record group. See `stream_shard`."""
    for shard in shards(group)[:limit_shards]:
        yield from stream_shard(shard.key, prefilter)


def resolve_title(record: dict[str, Any]) -> str | None:
    """Record-group title from a record's ancestor chain.

    RG titles are not encoded in the bucket layout; they only exist inside
    records.
    """
    for anc in record.get("ancestors", []):
        if anc.get("levelOfDescription") == "recordGroup":
            return anc.get("title")
    return None
