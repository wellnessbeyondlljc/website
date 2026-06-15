# WAI Lug Schema — Fast Path

> Full protocol: load `wai-lug-schema.md` for deep schema, PEV chains, spec lugs, execute-when gates.

**80% case: creating or updating a lug.** Use this file for quick reference.

---

## Storage Paths

```
WAI-Spoke/lugs/bytype/{type}/{status}/{id}.json
```

| Status | Path |
|--------|------|
| New | `bytype/{type}/open/{id}.json` |
| Active | `bytype/{type}/in_progress/{id}.json` |
| Done | `bytype/{type}/completed/{id}.json` |

---

## Essential Fields (every lug)

```json
{
  "id": "epic-name-20260101",
  "type": "task",
  "status": "open",
  "title": "5+ word descriptive title explaining intent or impact",
  "created_at": "2026-05-26T00:00:00Z",
  "gb": "claude-sonnet-4-6",
  "fw_ver": "3.0.0",
  "impact": 7,
  "effort": 2,
  "urgency": 3,
  "routed_to": "LOCAL",
  "model_fit": "haiku",
  "va": "build",
  "perceive": ["What to read before starting"],
  "execute": ["Concrete numbered steps"],
  "verify": ["How to confirm done"]
}
```

---

## Type Quick Reference

| Type | Use for |
|------|---------|
| `task` | Work item |
| `bug` | Defect |
| `feature` | New capability |
| `epic` | Multi-session effort |
| `implementation` | Non-trivial execution batch |
| `signal` | User-action-required alert → write to hub inbox |
| `spec` | Living behavior documentation |
| `chain` | Claimable multi-session coordination unit — claim before planning, defer overflow |
| `session-summary` | End-of-session record |

---

## Routing

| Value | Meaning |
|-------|---------|
| `LOCAL` | This spoke only |
| `FRAMEWORK` | Framework-level change |
| `SPOKE/{id}` | Another spoke |

Signals: write directly to `{hub_path}/WAI-Hub/signals/incoming/` — do NOT use `routed_to`.

---

## ID Generation

```
id = sha256(title)[:12]
# Named: "epic-slimdown-20260227", "lug-fnd-abc12345"
```

---

## Key Defaults

| Field | Default |
|-------|---------|
| `urgency` | 3 (NORMAL) |
| `model_fit` | `"haiku"` |
| `impact` | `5` |
| `effort` | `2` |
| `routed_to` | `"LOCAL"` |

**`gb` must be the actual model ID** (e.g. `claude-sonnet-4-6`) — never a name or alias.

---

## Contract Fields (lease + verify + provenance)

A lug is a hole in a [pattern](wai-pattern.md) (the contract). These fields make it leasable and verifiable. Full detail: `wai-lug-schema.md`.

| Field | Meaning |
|-------|---------|
| `held_by` | session_id holding the lease, or null |
| `held_at` | ISO-8601 claim time, or null |
| `lease_ttl_hours` | lease duration (default 4); `held_at + ttl` = expiry |
| `verify_mode` | how this lug's `verify[]` is certified: `mechanical` \| `attested` \| `human` |
| `provenance` | `{source_lugs[], source_teachings[]}` — inputs that led to this lug |

- **Lease = generalized chain-claim** — atomic claim via `wai_claims` PK (fallback `claims-local.json`). Readers skip a lug held by a *live* session; expired leases auto-release at wakeup/dispatch. **Bias to done:** if you can't finish within the TTL, emit a partial bolt and release — don't squat.
- **verify_mode** drives the pattern's certification: `mechanical` runs `verify[]` as a runnable assertion; `attested` requires a named verifier to sign; `human` requires Mario to sign. Nothing certifies uncertified.

---

## Lifecycle Move Commands

```bash
# Open → in_progress
mv WAI-Spoke/lugs/bytype/task/open/{id}.json WAI-Spoke/lugs/bytype/task/in_progress/{id}.json

# in_progress → completed
mv WAI-Spoke/lugs/bytype/task/in_progress/{id}.json WAI-Spoke/lugs/bytype/task/completed/{id}.json
```
