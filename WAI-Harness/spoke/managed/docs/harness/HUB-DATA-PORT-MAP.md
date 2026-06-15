# Hub → mywheel: Complete Data-Port Map + Routing Resolution

**Authored:** S session-20260610-1746 (framework) · **Status:** DESIGN-AUTHORITATIVE
**Resolves:** `gap-hub-migration-directives-incomplete-data-port-v1` (P1, hub→framework) AC1–AC4
**Parent epic:** epic-harness-v4-self-certifying-v1 · **Feeds:** V4-COMPLETE-PLAN Phase C (hub independence) + Phase E/F (routing + retirement)
**Owner split:** framework OWNS this map + the routing design; hub EXECUTES the port from it; Basher distributes the delivery-path resolver change.

This doc closes the two gaps the hub raised: (1) the migration directives ported only the SERVING subset, leaving the hub's OPERATIONAL data stranded; (2) mywheel had no canonical host locations and routing still resolves to the legacy framework/hub trees. Decisions baked in (user, this session): **new hub = `mywheel/WAI-Harness/hub`**, **harness-dev home = mywheel**, **framework + old-hub retire** (dormant, on disk).

---

## 1. Answering the hub's three open design questions

**Q1 — The hub's two identities (WAI-Spoke node-ops vs WAI-Hub serving): stay two trees or merge?**
**Two trees, not merged — they map 1:1 onto the layout mywheel already has.** `WAI-Harness/` is built with exactly this split:
- **Serving role** (fleet-facing: registry, teachings_repo, fleet advisors, parity, model-routing) → **`mywheel/WAI-Harness/hub/{managed,local}`**. Largely done (serving subset copied, gate GREEN).
- **Node/spoke-identity role** (the hub operates as a spoke: its own sessions, WAI-State, lug queue, node advisors, initiatives, savepoints) → **`mywheel/WAI-Harness/spoke/{managed,local}`**. mywheel-as-a-spoke *is* the hub node. This is the half that was never ported.

**Q2 — Since mywheel replaces framework, do former-framework-routed destinations now resolve to mywheel? Is framework/ retired like wai-hub?**
**Yes to both.** framework + old-hub become dormant (V4-COMPLETE Phase F, human-gated). Every destination that resolved to `wheelwright-framework` (fleet coordination, canonicalization/curation, Trainer escalation target) and to `wheelwright-hub` now resolves to **mywheel**. See §3.

**Q3 — Is mywheel where sessions actually run now, or a served-blueprint home while ops continue in wai-hub until retirement?**
**mywheel is the live node** (master blueprint + hub serving + hub node-ops) once the port + routing land. `wheelwright/hub` is kept intact ONLY as a just-in-case fallback through Phase F, then dormant. No live operation continues from the old tree after the port verification (§4) passes.

---

## 2. Canonical host-location map (AC1 + AC2) — every hub data class, old → new

Secrets stay in env (never copied). Regenerable cruft (git history, caches, `__pycache__`, vector/graph indexes that rebuild) is left behind. Every row below is operational data that MUST port.

### 2a. SERVING data → `mywheel/WAI-Harness/hub/local/`
| Data class | Old (`wheelwright/hub/…`) | New (`mywheel/WAI-Harness/hub/local/…`) | Status |
|---|---|---|---|
| Fleet registry | `hub-registry.json` | `registry/hub-registry.json` (+ a top alias if tools expect it) | mostly done |
| teachings_repo | `WAI-Hub/teachings_repo/` | `teachings_repo/` | done |
| teachings (published) | `WAI-Hub/teachings/` | `teachings/` | done |
| learnings | `WAI-Hub/learnings/` | `learnings/` | done |
| Fleet advisors (Octo, Trainer, Assessor, Gardener, Spinner, Cartologist, Quartermaster, Navigator-hub) | `WAI-Hub/advisors/*` | `octo/` + advisor dirs | partial (octo done; verify Trainer/Assessor live) |
| model-routing / provider matrix | `WAI-Hub/model-routing/` | `model-routing/` | done |
| parity state | `WAI-Hub/parity/` | under `WAI-Hub/` or `registry/` | verify |
| hub scripts/tools | `WAI-Hub/scripts,tools/` | `scripts/`, `tools/` (HUB_DIR-converted) | done |

### 2b. NODE / spoke-identity data → `mywheel/WAI-Harness/spoke/local/` (and `spoke/advisors/`)
**This is the stranded half. None of it is ported yet — targets defined here.**
| Data class | Old (`wheelwright/hub/WAI-Spoke/…`) | New (`mywheel/WAI-Harness/spoke/local/…`) |
|---|---|---|
| Node identity state | `WAI-State.json` | `WAI-State.json` |
| Lug queue — incoming (FLEET ROUTES HERE) | `lugs/incoming/` (7 active) | `lugs/incoming/` |
| Lug queue — outgoing | `lugs/outgoing/` (22) | `lugs/outgoing/` |
| Lug queue — completed | `lugs/completed/` (16) | `lugs/completed/` |
| Lug queue — processed | `lugs/processed/` (58) | `lugs/processed/` |
| Lugs — bytype / epics / inbox | `lugs/{bytype,epics,inbox}/` | `lugs/{bytype,epics,inbox}/` |
| Lug index | `lugs/WAI-LugIndex.jsonl` | `lugs/WAI-LugIndex.jsonl` |
| Lug-attached learnings/reference | `lugs/{learnings,reference}/` | `lugs/{learnings,reference}/` |
| Sessions / tracks | `sessions/` | `sessions/` |
| Savepoints (resume state) | `savepoints/` | `savepoints/` |
| Initiatives | `initiatives/` | `initiatives/` |
| Node advisors (the hub's own Ozi etc.) | `advisors/` | **`spoke/advisors/`** (sibling of `local/`) |
| seed / runtime / pathgraph | `{seed,runtime,pathgraph}/` | `local/{seed,runtime,pathgraph}/` |

> The hub's **fleet-facing incoming is the NODE's incoming** — hub-directed work lands in `spoke/local/lugs/incoming/` and the hub works it as a node. There is no separate "serving incoming."

---

## 3. Routing resolution to mywheel (AC3)

Two independent fixes; both required for a post-fix lug to land in mywheel.

**3a. Registry repoint (the destination).**
- **Register `mywheel`** in `hub-registry.json` `wheels[]` (it is currently absent — root cause of "deliveries land in framework/").
- Set the hub node entry `path = /home/mario/projects/wheelwright/mywheel` (repoint `wheelwright-hub`, or add `mywheel` as the hub node and mark `wheelwright-hub` dormant).
- Redirect former-framework destinations: any `routed_to: SPOKE/wheelwright-framework` (curation, fleet coordination, canonicalization) now resolves to the mywheel node. Mark `wheelwright-framework` dormant at Phase F.
- This is the work tracked as `task-mywheel-registry-and-cutover-v1` — **HARD human gate on teardown**, but registration + repoint can land ahead of teardown.

**3b. Delivery-path resolution (the address within the destination).**
- Lug delivery currently hardcodes `{path}/WAI-Spoke/lugs/incoming/`. For a v4-only node (mywheel) that path does not exist.
- **Fix:** delivery must resolve the target's incoming via the same harness-mode resolver built this session — `tools/wai_paths.py` → `category(target_path, "lugs")/incoming`, yielding `mywheel/WAI-Harness/spoke/local/lugs/incoming/`.
- Affected: `dispatcher.py` / any tool that composes a delivery path, and the CLAUDE.md/AGENTS.md "deliver to `{path}/WAI-Spoke/lugs/incoming/`" rule (update the doctrine string too).
- Owner: framework builds the resolver call into the delivery tools (`framework/tools/`); Basher distributes any `.claude` command that encodes the path. This is a direct extension of the Phase B port — **add `dispatcher.py` + delivery tools to the Phase B port list.**

---

## 4. Complete-port verification command (AC4)

The hub executes the port (rsync/cp per the map), then proves zero stranded operational data. Verification (run from `wheelwright/`):

```bash
# A. every NODE data class exists at the new home (non-empty where source was non-empty)
for d in lugs/incoming lugs/outgoing lugs/completed lugs/processed lugs/bytype \
         lugs/epics lugs/inbox sessions savepoints initiatives; do
  src="hub/WAI-Spoke/$d"; dst="mywheel/WAI-Harness/spoke/local/$d"
  s=$(find "$src" -type f 2>/dev/null | wc -l); t=$(find "$dst" -type f 2>/dev/null | wc -l)
  [ "$s" -le "$t" ] && echo "OK   $d ($s→$t)" || echo "FAIL $d ($s→$t)  STRANDED"
done
test -f mywheel/WAI-Harness/spoke/local/WAI-State.json && echo "OK   WAI-State.json" || echo "FAIL WAI-State.json"
test -f mywheel/WAI-Harness/spoke/local/lugs/WAI-LugIndex.jsonl && echo "OK   LugIndex" || echo "FAIL LugIndex"

# B. routing proof — deliver a probe lug, confirm it lands in mywheel not framework/ or hub/
#    (after 3a+3b land) deliver test-route-probe-v1 to the hub node; assert:
#    test -f mywheel/WAI-Harness/spoke/local/lugs/incoming/test-route-probe-v1.json
#    && ! test -f framework/WAI-Spoke/lugs/incoming/test-route-probe-v1.json

# C. old tree holds no UN-PORTED operational data (identity/queue) — serving fallback may remain until Phase F
echo "remaining active lugs in OLD hub node:"; find hub/WAI-Spoke/lugs/incoming -name '*.json' | wc -l
```
GREEN = every node class ported (A), probe routes to mywheel (B), and the old incoming is drained (C). Serving data in `wheelwright/hub` stays as a Phase-F fallback; node/operational data must be zero-stranded here.

---

## 5. Framework deliverables checklist (what this doc + follow-on lugs satisfy)
- [x] **AC1** host-map enumerates every hub data class, old→new (§2) — no class implicit.
- [x] **AC2** canonical mywheel host locations defined in the blueprint (§2, this doc lives in the harness blueprint).
- [~] **AC3** routing design defined (§3); EXECUTION = register mywheel + repoint (`task-mywheel-registry-and-cutover-v1`, human-gated) + delivery-path resolver (extend Phase B port to `dispatcher.py`).
- [x] **AC4** verification command provided (§4).
- [ ] **Re-issue corrected directives to the hub** = a change-lug to the hub node carrying §2 map + §4 verification, replacing the serving-only directives. (Created alongside this doc.)

## 6. Caveats carried in (P12)
- The registry repoint + framework-dormant are behind the **hard human teardown gate** — registration/repoint can land first; teardown does not, until sign-off.
- The 4 handoff/confirm lugs the hub already delivered to `framework/` are at the wrong home under the new model; once 3a+3b land they should be re-emitted from the hub's outgoing to the mywheel node (hub holds the copies).
- §3b reuses `tools/wai_paths.py` (built this session) — delivery tools are NOT yet ported; add them to the Phase B port surface.

---

## 7. Serving-CODE vs Operational-DATA classification (P1 boundary, epic-mywheel-complete-functionality-migration-v1)

**Authored:** session-20260610-2217 P1-EVALUATION · **Companion artifact:** `WAI-Spoke/harness/boundary-map.json` (file-level census: every tracked file in framework + hub classified, `totals.unclassified = 0`).

§2 above mapped the hub's operational DATA. This section adds the missing half — the serving CODE boundary — so P2 migrates exactly one canonical copy of every functional asset and leaves data as data.

**The rule (central split):**
- **CODE = MANAGED** → version-controlled in the mywheel blueprint, distributed + MANIFEST-verified. A `.py` implementation, adapter, hook, skill/command prompt, schema, charter/prompt that *defines behavior*, test suite, or authored config (e.g. `work-classes.json`) is CODE — regardless of extension.
- **DATA = OPERATIONAL-LOCAL** → `local/` trees, gitignored at distribution targets, ported once per §2 then accumulated in place. A `.json`/`.jsonl` cache, recommendation, learning, teaching file, session track, lug queue, registry state, parity snapshot, or *fetched* provider matrix is DATA — even when it sits next to code.
- Two further classes complete the taxonomy: **SELF-BUILT-LOCAL** (per-spoke advisor *instances* under `WAI-Spoke/advisors/{name}/` — Phase-2.5 doctrine: each spoke's Ozi builds its own crew; only the advisor *framework* — `advisor_manager.py`, `evolution_engine.py`, `schema/advisor-schema-v1.yaml`, `coverage-model.yaml`, `departments.json` — is blueprint) and **DROP** (deprecated SIGNAL system 536 files, archives, stale mirrors, one-off migration/audit scripts, `__pycache__` — preserved only in archived repo git history).

**Per-area MANAGED-code targets (old → mywheel):**

| Serving code class | Old location | mywheel target |
|---|---|---|
| Hub-council advisor code (16 advisors: impls, adapters, scripts, skills, charters/prompts) — 55 files | `hub/WAI-Hub/advisors/*` | `WAI-Harness/hub/managed/advisors/{name}/` |
| Hub serving tools — 46 files | `hub/tools/` + `hub/WAI-Hub/tools/` | `WAI-Harness/hub/managed/tools/` |
| Hub model-routing code (`grab.py`, grabbers, `work-classes.json`) | `hub/model-routing/` | `WAI-Harness/hub/managed/model-routing/` (fetched `registry.json` + usage telemetry → `hub/local/model-routing/`) |
| Hub skills, advisor-templates, design docs, launch, scripts, octo.py, tests, `.claude` | `hub/WAI-Hub/{skills,advisor-templates,docs}/`, `hub/{launch,scripts,octo,tests,.claude}/` | `WAI-Harness/hub/managed/{skills,advisor-templates,docs,launch,scripts,octo,tests,.claude}/` |
| Spoke orchestration tools — 113 `.py` (87 MANAGED still stranded; 2 DROP: `v4_migrate.py`, `v4_skeleton.py`) + 7 root-level `wai_ozi*.py`/`wai_goal_queue.py` | `framework/tools/`, `framework/*.py` | `WAI-Harness/spoke/managed/tools/` |
| Skills/commands blueprint — 105 canonical | `framework/templates/commands/` | `WAI-Harness/spoke/managed/.claude/commands/` (104 present — diff-refresh; `wai-track.md` superseded-in-progress, take post-rewrite version) |
| Hooks — 11 | `framework/.claude/hooks/` | `WAI-Harness/spoke/managed/.claude/hooks/` |
| Advisor-framework code (NOT instances) | `framework/WAI-Spoke/advisors/{advisor_manager.py,evolution_engine.py,schema/,coverage-model.yaml,departments.json}` | `WAI-Harness/spoke/managed/` |
| Shared serving code + tests + schemas + supabase migrations + scripts + wilbur code + crew/config | `framework/{shared,tests,schemas,supabase,scripts,wilbur,crew,config,wai,managed}/` | `WAI-Harness/spoke/managed/…` |
| Harness-dev assets (benchmarks, test-bench, docs, examples, design docs incl. this map) | `framework/{benchmarks,test-bench,docs,examples}/`, `framework/WAI-Spoke/harness/` | `WAI-Harness/dev/…` (harness-dev home = mywheel) |

**Confirmation:** every data class enumerated in §2a/§2b is **OPERATIONAL-LOCAL** under this taxonomy — nothing in §2 is blueprint code, and the §2 targets (`hub/local/`, `spoke/local/`) stand unchanged.

**Dedupe warning for P2 (do not port three copies):** `framework/templates/commands/` (canonical), `framework/.claude/commands/`, `framework/spoke/codebase/templates/commands/`, and `framework/hub/` vs `hub/WAI-Hub/` hold overlapping renders with version skew (e.g. `framework/hub/.../navigator/adapters/` has `_chat_contract.py`/`_rate_limiter.py`/`nvidia.py` that `hub/WAI-Hub/.../adapters/` lacks). P2 collapses to ONE canonical copy per file, newest wins, MANIFEST stamps the result. Open boundary calls (5) are listed in `boundary-map.json → open_questions_for_user`.
