# Base Harness Adoption Kit

**Canonical source.** This directory is the framework-authored source of the bootstrappable harness. The hub (`hub/teachings_repo/spoke/base/`) receives a copy via the distribution path; spokes adopt from there.

## Model: base + ≤10 patches

The harness is versioned. A spoke is never more than `base + ≤10 patches` behind, so it can level up from any prior state in **one** focused session by running the current base kit — not by replaying history.

```
templates/harness-base/
  index.json          # current base_version + ordered file list + adoption_check
  v3.0.0/             # the kit: read 00→06 in order
    00-manifest.json  # machine-readable components + checks
    01-orient.md      # why + value
    02-detect.md      # greenfield vs brownfield
    03-bootstrap.md   # greenfield establish
    04-migrate.md     # brownfield subsume + idempotent re-assert
    05-hygiene.md     # ongoing rules + patch grooming
    06-verify.md      # component checks → emit adoption bolt
  README.md           # this file
```

## The 10-item cap policy (non-negotiable)

The active patch set must never exceed **10** entries beyond the current base.

- **Why:** a backlog >10 means an Ozi cannot catch up in one session and the harness has drifted from its own documentation. Teaching publication is a commitment to implement, not a staging area.
- **At the cap:** the publisher (framework) must cut a new base that absorbs the existing patches **before** adding any new one.
- **Cutting is human-gated:** `tools/base_cut_draft.py` auto-assembles the candidate base + a reconciliation report lug; a human approves; then patches are archived (`absorbed_in_base_version`) and the count resets to 0.

## Adoption is bolt-certified

Running the kit ends by emitting an **adoption bolt** (`kind: "adoption"`) — adoption is verified done, not presumed done. The bolt id is recorded as `WAI-State.json._harness.base_bolt_id`.
