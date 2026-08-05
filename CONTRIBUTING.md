# Contributing

## Setup

```bash
pip install -e ".[dev]"    # or: uv sync --extra dev
pytest -m "not network"    # offline
pytest -m network          # hits the public bucket
ruff check . && ruff format .
mypy
```

## The bar for a finding

This corpus readily produces compelling patterns that dissolve on inspection. Five
dramatic hypotheses were refuted during the initial survey. A finding needs:

1. **A denominator.** Restricted counts without their unrestricted baseline are
   uninterpretable. `inventory.Summary` enforces this; don't route around it.
2. **Replication across ≥3 record groups.** One group is an anecdote. The edit-intensity
   result held in two agencies and *inverted* in the third — that inversion is the
   interesting part, and it only appeared because of replication.
3. **Boring explanations ruled out first.** Bulk import, schema migration, grant cycle,
   one archivist's project, systems change. Escalate only after these fail.
4. **A stated falsification condition.** What observation would kill it?

Refutations are as valuable as discoveries and go in the same document.

## Two-refutation rule

If two consecutive hypotheses die inside the same field or theme, step back and review the
**frame**, not just the next hypothesis. Loose hypotheses inside a locked frame still
produce tunnel vision. See `AGENTS.md` §0.

## Ethics

Aggregate patterns about agencies are the product. Profiles of named private individuals
are not. `FOIA (b)(6) Personal Information` flags exist because living people are in those
files — treat them as a signal to aggregate, not to drill down. PRs that assemble
person-level dossiers will be declined.

## Don't commit data

`data/` is gitignored. Shards are 50 MB+; vintages are hundreds of GB.
