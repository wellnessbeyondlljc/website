# 06 — Verify: prove adoption + emit the adoption bolt

Adoption is not done until it is **certified**. Run the component checks, run the dead-code scan, then emit an adoption bolt and record it in the ledger.

## 1. Run component checks

For each component in `00-manifest.json`, run its `check`. Collect results into a checks list:

```json
[
  {"component": "WAI-Spoke/WAI-State.json", "mode": "mechanical", "result": "pass", "note": "parses"},
  {"component": ".claude/hooks", "mode": "mechanical", "result": "pass"},
  {"component": "_harness ledger", "mode": "mechanical", "result": "pass"}
]
```

A component whose check exits non-zero is `result: "fail"`; a not-applicable component is `result: "pending"`, `"skipped": true`.

## 2. Run the harness dead-code scan

```bash
python3 tools/harness_deadcode_scan.py --spoke-path .
```

It builds the tool→caller reference graph and reports ORPHANED tools + BROKEN skill→tool refs. Add its summary as one check item (`component: "deadcode-scan"`). Surface findings — adoption is the right moment to catch dead zones.

## 3. Emit the adoption bolt

```bash
python3 tools/verify_engine.py emit-adoption \
  --session-id {SESSION_ID} --base-version 3.0.0 \
  --checks @/tmp/adoption-checks.json --spoke-path .
```

The bolt lands in `WAI-Spoke/bolts/bytype/adoption/recorded/`. Its id is `bolt-{session}-adoption-base-3.0.0`. `certified` = every executed component passed; `partial` = something is still unverified (record what remains).

## 4. Update the ledger

Write the bolt id and timestamp into `WAI-State.json._harness`:

```json
"_harness": { "base_version": "3.0.0", "base_bolt_id": "bolt-{session}-adoption-base-3.0.0", "patches_adopted": [], "patches_available": "{count from hub base/teachings/index.json}", "fw_ver": "{derived}", "last_adoption_check": "{now ISO}" }
```

**Derive `fw_ver`** (reproducible fleet-state hash): collect the `fingerprint` of each adopted patch from `base/teachings/index.json`, then `fw_ver = MD5("{base_version}.{alpha-sorted adopted fingerprints}")[:12]` (with no patches: `MD5("{base_version}.")[:12]`). Two spokes on the same base + same patches derive an identical `fw_ver` regardless of order. See `wai-lug-schema.md` § Series Versioning.

## 5. Then apply patches

With the base certified, apply any unadopted entries in the hub `base/teachings/index.json` in order (see `05-hygiene.md`), appending each id to `_harness.patches_adopted`.

**Adoption complete.** The spoke is at base 3.0.0; backlog is bounded at ≤10 patches forever.
