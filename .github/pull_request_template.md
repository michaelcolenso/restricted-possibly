## What changed

## Checklist

- [ ] `pytest -m "not network"` passes
- [ ] `ruff check . && ruff format --check .` passes
- [ ] No corpus data committed (`data/`, `*.jsonl`, shard files)
- [ ] If this adds a finding: denominator, replication count, and falsification
      condition are stated in `docs/FINDINGS.md`
- [ ] If this changes schema assumptions: a test guards the assumption
