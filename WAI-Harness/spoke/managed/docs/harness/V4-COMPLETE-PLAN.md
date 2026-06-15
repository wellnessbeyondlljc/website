# V4 Complete — Native Sessions, Independent Hub, Framework/Old-Hub Retired

**Authored:** S46 (2026-06-10) · **Status:** APPROVED-FOR-NEXT-SESSION · **Owner driver:** framework, with Basher (hooks/distribution) + hub (its own migration)
**Mandate (user, S46):** V4 *completely* done, not partial. A **v4-native session must be possible** (greenfield AND brownfield). The **hub spun up + warmed with zero dependency on the old folder**. Same for **framework** — framework + old-hub are *on their way out*: kept on disk just-in-case, but **not active, not involved**.

---

## Definition of DONE (the only acceptance that matters)
1. **V4-native session works** — a session in `WAI_HARNESS_MODE=v4-only` runs the full cycle (wakeup → work → closeout → track → savepoint) **entirely on v4 trees** (`WAI-Harness/spoke/local`), with **zero reads/writes to `WAI-Spoke/`**. Proven on: (a) a **greenfield** spoke, (b) a **brownfield upgrade** (v3→v4-native), (c) a **brownfield adopt** (non-WW repo → v4-native).
2. **Hub independent** — the hub runs every service (registry, teaching delivery, parity, advisors incl. Trainer/Assessor) **from its new location**; move `wheelwright/hub/WAI-Hub` aside and the hub still works. No symlink into the old folder.
3. **Framework + old-hub dormant** — removed from the active fleet (registry), nothing's `hub_path`/`master` points at them, set `v3-only`/dormant, harness-dev home relocated. Kept on disk, not active.
4. **Fleet on v4-native + new hub** — `cutover_readiness.py` GREEN **and** a new native-session check passes for every active registry spoke.

## Current state (entering this plan)
- v4 activated (markers) on 27/29 registry spokes, but **not running** — the v4 steps live in `.claude/hooks/session-start.sh` which most spokes don't invoke (they run `WAI-Spoke/_hooks/session-start.sh`, pure v3). **Basher P0 lug `change-basher-wire-v4-into-registered-sessionstart-hook-v1` fixes this** (in flight).
- Coexistence only: even when the v4 hook runs it `exec`s the v3 wakeup. **No native session yet.**
- `harness_mode.sh` already resolves `coexist|v4-only|v3-only` via `$WAI_HARNESS_MODE` — the switch exists; ceremonies/tools just aren't v4-path-aware (6 tools still read `WAI-Spoke/`, 6 read v4 `local/`).
- Hub stood up via **symlink-bridge** to the old folder (interim — must become a real copy).
- `harness_init.py` + `v4_migrate.py` exist in `framework/tools` (greenfield/adopt/upgrade engines) but not yet in master managed.
- Epic `epic-harness-v4-self-certifying-v1`: 26 [x] / 21 [~]. Harness VERSION `4.0.0-pre.2`.

---

## Phases (sequenced; each gated; AP-tested; VERSION-bumped; canonicalized to master)

### Phase A — Make v4 RUN  *(Basher P0, IN FLIGHT)*
Wire the v4 steps into the **registered** SessionStart hook fleet-wide; register SessionStart on basher/hub/client spokes that lack it; emit a visible `[v4 ACTIVE]` indicator; remove the dead `.claude/hooks` copies.
**Gate:** a fresh session on every registry spoke runs pull+activate and shows `[v4 ACTIVE]`. *(Owner: Basher. Lug delivered.)*

### Phase B — V4-NATIVE session  *(the core framework build)*
Make session-start + every ceremony + every state tool **resolve its WAI root by mode**:
- Build `tools/wai_paths.py` → `resolve_wai_root(spoke_root)`: `v4-only` → `WAI-Harness/spoke/local`; `v3`/`coexist` → `WAI-Spoke`. Single source all ceremonies/tools call.
- Port the **registered session-start/wakeup** to emit the `<wai-session-init>` briefing from the resolved root (native in v4-only, no `exec` of the v3 hook).
- Port **closeout, savepoint, track** (and the 6 v3-path tools) to the resolver — write/read v4 `local/` in v4-only.
- v3 trees are **read-only fallback**, never required in v4-only.
**Gate:** set `WAI_HARNESS_MODE=v4-only` on a pilot (framework's own install) → full wakeup→work→closeout→track→savepoint cycle runs with **zero `WAI-Spoke/` access** (verify by temporarily renaming `WAI-Spoke/` — session still works). *(Owner: framework builds; Basher distributes hook edits.)*

### Phase C — Hub independence (no old-folder dependency)
Subsume the hub's **valuable data** (registry, advisors incl. Trainer/Assessor, parity, teachings, learnings, model-routing) as a **real copy** into the new hub location; drop the symlink; run all hub services from there. Secrets stay in env (never copied); cruft (git history, indexes, caches, logs) left behind.
**Decision (recommend): new hub = `mywheel/WAI-Harness/hub`** (operational data in `hub/local/`, gitignored) — mywheel = master + hub node, the one-folder end-state. (Alt: dedicated hub repo — hub may counter-propose.)
**Gate:** move `wheelwright/hub/WAI-Hub` aside → hub still serves registry/teaching/parity/advisors from the new location; `cutover_readiness new_hub_serves` GREEN from the **real copy** (no symlink). *(Owner: hub executes `change-hub-subsume-valuable-data-drop-symlink-v1`; framework verifies independence.)*

### Phase D — Greenfield + Brownfield native engines
Bring `harness_init.py` + `v4_migrate.py` into master managed and make each produce a **v4-only** spoke:
- **Greenfield:** bootstrap a fresh spoke from the mywheel blueprint with **no `WAI-Spoke/`** — born v4-native.
- **Brownfield upgrade:** v3 spoke → migrate state into v4 `local/` → flip `v4-only` (v3 retained as dormant fallback).
- **Brownfield adopt:** existing non-WW repo → v4-native + gap report (closes **AC31**).
**Gate:** all three scenarios yield a spoke that passes the Phase-B native-session check on a throwaway target. *(Owner: framework.)*

### Phase E — Fleet to v4-native + repoint + new hub
Basher convoy rolls the v4-only migration + `hub_path` repoint (→ new hub) across the active fleet (active-30d first; client spokes warmed, activation on the human gate).
**Gate:** `cutover_readiness.py` GREEN **and** the native-session check passes for every active registry spoke. *(Owner: Basher convoy; framework verifies.)*

### Phase F — Retire framework + old-hub (dormant, kept just-in-case)  *(HUMAN GATE)*
- **Relocate harness-dev home** off framework: the test suite + tooling authoring move to mywheel (or a dedicated `harness-dev` spoke) so framework is not needed to evolve the harness.
- **Deactivate** framework + `wheelwright/hub`: remove from the active registry, ensure no spoke's `hub_path`/`master` resolves to them, set them `v3-only`/dormant. **Keep on disk** (just-in-case), not active.
**Gate (hard human):** a full fleet session cycle runs with framework + old-hub dormant/untouched; a `no-legacy-dependency` check finds zero active references; then sign-off. *(Owner: framework + Basher; human gate.)*

---

## New verification to BUILD (the done-detector)
Extend `cutover_readiness.py` (or a new `v4_native_check.py`): for each registry spoke assert (a) session runs in `v4-only`, (b) zero `WAI-Spoke/` dependency (rename-test or static scan), (c) `hub_path` → new hub, (d) no ref to framework/old-hub. GREEN here = DONE.

## Cross-cutting discipline (every phase)
AP tests at birth · full suite green · **bump `mywheel/WAI-Harness/VERSION`** · canonicalize to master + recut MANIFEST + commit `wai-mywheel` · use **registry** for fleet paths (never fs-walk) · never touch `_archive` · changes to other spokes travel as lugs + notice.

## Open decisions to confirm at kickoff
1. **New hub location:** `mywheel/WAI-Harness/hub` (recommended) vs dedicated hub repo.
2. **Harness-dev home after framework retires:** mywheel vs a new `harness-dev` spoke.
3. **Adopt test target:** which real non-WW repo for Phase D brownfield-adopt.

## Resume order next session
A (confirm Basher landed) → **B (native — the keystone build)** → C (hub independence) → D (engines) → E (fleet roll) → F (retire, human gate). Phase B is the long pole; start there.
