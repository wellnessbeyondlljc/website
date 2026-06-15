# 01 — Orient: What you are adopting and why

You are reading the **Base Harness Adoption Kit v3.0.0**. Read files 01→06 in order. By the end you will have stood up (or migrated to) a working WAI harness on this repository and emitted an **adoption bolt** proving it.

## Why this exists

A WAI spoke accumulates teachings (small behavior deltas) over time. Left ungroomed, a spoke can fall dozens of teachings behind and an agent cannot catch up in one session. The harness solves this by being **versioned**:

- The **base** is the whole harness baked into one bootstrappable kit (this directory).
- **Patches** are a bounded set of ≤10 deltas published since the base was cut.
- When patches reach 10, the publisher cuts a new base that absorbs them, and the count resets.

**Consequence you can rely on:** a spoke is never more than `base + ≤10 patches` behind. To level up from *any* prior state, you run this kit **once** — you do not replay history. Old teachings predating this base are already subsumed here and archived, so never go looking for them.

## What the harness gives this repo

- **Persistent work state** in lugs (not scratch files or tasks) — survives sessions (P11).
- **A per-turn track ledger** — the continuity substrate across compaction.
- **Verifiable transitions** — work, ceremony, and this very adoption are certified by bolts (verified done, not presumed done).
- **Session hooks** — wakeup brief, compaction preservation, test gate, destructive-command guard.
- **Skills** — the wakeup / savepoint / closeout protocols and the lug system.

## The prime directive while adopting

Be **idempotent**. Every step is written as "ensure this state." Running the kit twice changes nothing the second time. If something already exists and is correct, leave it. If it exists and is wrong, reconcile it. When genuinely unsure whether to overwrite real data, **stop and write a notation lug** asking for proper handling rather than clobbering.

→ Continue to `02-detect.md`.
