"""Normalization across the two NARA schemas.

The corpus contains two incompatible serializations:

**v2** (`descriptions/`, current) -- JSONL, one record per line, flat-ish::

    {"record": {"naId": 123, "accessRestriction": {"status": "Unrestricted"}}}

**v1** (`backups/descriptions*/`, 2021-2022) -- a single malformed JSON blob
per shard, wrapped as ``{[ {...}, {...} ]}``, with records nested under
``description.{series|fileUnit|item|...}`` and controlled terms represented as
``{"naId": ..., "termName": ...}`` objects rather than bare strings.

``naId`` is stable across both and is the only reliable join key.

.. warning::
   ``recordHistory`` (per-record edit timestamps) exists **only in v1**. It was
   dropped in the v2 migration and is absent from all current data. Timestamp
   forensics are therefore limited to the 2021-2022 vintages. Re-check each new
   snapshot in case NARA restores it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RESTRICTED = {"Restricted - Fully", "Restricted - Partly", "Restricted - Possibly"}

#: `Restricted - Possibly` means "not yet reviewed" -- a processing-backlog
#: marker, not a withholding decision. Keep it separable from real restrictions.
UNREVIEWED = "Restricted - Possibly"


def load_v1(path: str | Path) -> list[dict[str, Any]]:
    """Parse a v1 shard, repairing the malformed ``{[ ... ]}`` wrapper."""
    raw = Path(path).read_text(encoding="utf-8", errors="replace").strip()
    if raw.startswith("{[") and raw.rstrip().endswith("]}"):
        raw = raw[1 : raw.rstrip().rindex("}")]
    return json.loads(raw)


def _term(value: Any) -> Any:
    """v1 encodes controlled terms as {naId, termName}; v2 uses bare strings."""
    if isinstance(value, dict) and "termName" in value:
        return value["termName"]
    return value


@dataclass
class Restriction:
    status: str | None = None
    exemptions: list[str] = field(default_factory=list)
    security_classification: str | None = None
    note: str | None = None

    @property
    def is_restricted(self) -> bool:
        return self.status in RESTRICTED

    @property
    def is_unreviewed(self) -> bool:
        return self.status == UNREVIEWED


def parse_restriction(access: dict[str, Any] | None) -> Restriction:
    """Read `accessRestriction` from either schema.

    The ``note`` field carries the actual legal basis and is frequently the
    only place an anomaly is explained -- e.g. the restriction code ``Other``
    is meaningless alone, while its note cites the statute. Always capture it.
    """
    if not access:
        return Restriction()
    specifics = access.get("specificAccessRestrictions") or []
    if isinstance(specifics, dict):  # v1 sometimes single-valued
        specifics = [specifics]
    if not specifics:  # v1 array form
        arr = access.get("specificAccessRestrictionArray") or {}
        inner = arr.get("specificAccessRestriction") if isinstance(arr, dict) else None
        specifics = [inner] if isinstance(inner, dict) else (inner or [])

    exemptions, classification = [], None
    for s in specifics:
        if not isinstance(s, dict):
            continue
        if (r := _term(s.get("restriction"))) is not None:
            exemptions.append(r)
        if (c := _term(s.get("securityClassification"))) is not None:
            classification = c

    return Restriction(
        status=_term(access.get("status")),
        exemptions=exemptions,
        security_classification=classification,
        note=access.get("note"),
    )


def physical(record: dict[str, Any]) -> dict[str, str]:
    """Media type, container ids, and holding facility from `physicalOccurrences`.

    This is what turns a naId into something a person can actually act on: which
    NARA facility holds the material and which container it sits in. Multiple
    occurrences are common (preservation vs reference copies); values are
    de-duplicated in first-seen order rather than collapsed to the first one.
    """
    media: list[str] = []
    containers: list[str] = []
    units: list[str] = []
    for po in record.get("physicalOccurrences") or []:
        if not isinstance(po, dict):
            continue
        for m in po.get("mediaOccurrences") or []:
            if not isinstance(m, dict):
                continue
            if (t := _term(m.get("specificMediaType"))) is not None:
                media.append(str(t))
            if (c := m.get("containerId")) is not None:
                containers.append(str(c))
        for u in po.get("referenceUnits") or []:
            if isinstance(u, dict) and (n := u.get("name")) is not None:
                units.append(str(n))
    return {
        "mediaType": "; ".join(dict.fromkeys(media)),
        "containers": "; ".join(dict.fromkeys(containers)),
        "location": "; ".join(dict.fromkeys(units)),
    }


def iter_v1_descriptions(items: list[dict[str, Any]]):
    """Yield (level, body) for each description in a parsed v1 shard."""
    for item in items:
        for level, body in (item.get("description") or {}).items():
            if isinstance(body, dict):
                yield level, body


def v1_modifications(body: dict[str, Any]) -> list[str]:
    """All modification timestamps for a v1 record. Empty for v2 records."""
    rh = body.get("recordHistory") or {}
    changed = rh.get("changed")
    if not isinstance(changed, dict):
        return []
    mod = changed.get("modification")
    if isinstance(mod, dict):
        mod = [mod]
    return [m["dateTime"] for m in (mod or []) if isinstance(m, dict) and m.get("dateTime")]


def v1_created(body: dict[str, Any]) -> str | None:
    return ((body.get("recordHistory") or {}).get("created") or {}).get("dateTime")


def year(value: Any) -> int | None:
    """Coverage/inclusive dates are {'year': N, 'logicalDate': ...} in v2."""
    if isinstance(value, dict):
        return value.get("year")
    return None
