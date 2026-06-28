# WAI Advisor Schema — Fast Path

> Full protocol: load `wai-advisor-schema.md` for pilot contract examples, shadow mode, evolution_risk, one-piloting-slot enforcement details.

**80% case: authoring or reviewing an advisor.** Key fields and lifecycle.

---

## Status Lifecycle

```
new → piloting → promoted
              → refined → piloting (next iteration)
              → removed
```

| Transition | Requires |
|-----------|---------|
| new → piloting | `pilot_contract` fully populated; no other advisor piloting |
| piloting → promoted | Evaluation run; `promote_if` criteria met |
| piloting → refined | Evaluation run; `refine_if` criteria met; `pilot_iteration++` |
| piloting → removed | Evaluation run; `remove_if` criteria met |

**One-piloting-slot rule:** Only one advisor per spoke may hold `status: piloting` at any time.

---

## Required Fields Quick Reference

| Field | Required | Notes |
|-------|----------|-------|
| `advisor.id` | Yes | Stable kebab-case, never changes |
| `advisor.name` | Yes | Human-readable, Title-case |
| `advisor.version` | Yes | SemVer — bump on behavioral change |
| `advisor.status` | Yes | `new\|piloting\|promoted\|refined\|removed` |
| `advisor.status_history` | Yes | Append-only `{status, at, by}` |
| `advisor.pilot_iteration` | When piloting/refined | Starts at 1 |
| `advisor.node_scope` | Yes | `spoke\|hub\|both` |
| `advisor.mission` | Yes | One paragraph, why it exists |
| `advisor.principles` | Yes (min 2) | Operating commitments |
| `advisor.inputs_required` | Yes | `data_stores`, `fields_consumed` |
| `advisor.patterns` | Yes (min 1) | Detection patterns |
| `advisor.outputs` | Yes (min 1) | `surface_at_wakeup\|emit_finding_lug\|…` |
| `advisor.escalation` | Yes | `lead`, `request_method` |
| `pilot_contract` | Yes when piloting/refined | Hypothesis, KPIs, decision criteria |
| `advisor.lifecycle` | Yes | `self_review_cadence`, `rollback_path` |

---

## Pattern fires_on Values

`wakeup` | `mid_session_on_demand` | `post_lug_create` | `post_commit` | `scheduled`

---

## Shadow Mode

`shadow: true` on a pattern → evaluates and logs but produces no visible finding.
`shadow: false` must be set **explicitly** — omitting the field is a schema error.

---

## Schema Source

`WAI-Spoke/advisors/schema/advisor-schema-v1.yaml`
