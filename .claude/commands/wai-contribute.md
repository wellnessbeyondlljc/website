# WAI Contribute

How to contribute a change to the harness / blueprint from any spoke.

## Purpose

The wheel runs a **curator model**: any spoke may change shared/blueprint code — framework is no longer the sole author. A change you make travels to the spokes that need it as a **complete change-lug** (a normal lug with a full account + attribution), handled by each receiving spoke **per its own policies**. Framework is the **convergence curator**: it reviews contributions and canonicalizes broadly-useful ones into the base template.

This skill is the protocol for emitting and receiving those change-lugs.

---

## The two channels (do not confuse them)

| Channel | Use for | Where it goes |
|---------|---------|---------------|
| **Change-lug** | An actual change you made (code/config/docs) that others need to know about, review, or maintain | The affected spoke's `WAI-Spoke/lugs/incoming/` (+ your `outgoing/`) |
| **Teaching** | A genuinely new, broadly-adoptable **pattern** everyone should adopt, OR retiring a named feature/doctrine (`deprecation-requires-teaching-v1`) | The Hub `teaching_repo` (separate concern; see `generate-teaching`) |

**Default to a change-lug.** Reserve teachings for pattern shifts and retirements. Ordinary change propagation does **not** need a teaching.

---

## When to Use

- You changed a shared tool, skill, schema, or doc and another spoke (or the whole fleet) should review/adopt it.
- You made any cross-spoke change (you must — see Sovereignty below).
- You want a provenance record of a local change.

---

## How to emit a change-lug

Use the helper — it stamps a complete lug and routes it correctly:

```bash
python3 tools/write_change_receipt.py \
  --reason "why the change was needed" \
  --summary "what was actually done" \
  --files path/one.py path/two.md \
  [--target <wheel_id|spoke_id>]   # omit for a local provenance record \
  [--commit <sha>]                 # default: current HEAD \
  [--agent <label>]                # autonomous runs; omit for human (git user) \
  [--dry-run]
```

What it does:
- **Local** (`--target` omitted): writes the change-lug to **your** `WAI-Spoke/lugs/outgoing/` as a provenance record.
- **Cross-spoke** (`--target` given): resolves the target's path via `hub-registry.json` and writes to **the target's** `WAI-Spoke/lugs/incoming/`, plus a copy to your `outgoing/` with `delivered_at`.
- Auto-fills `commit` (HEAD) and `authored_by` via `resolve_attribution()` — the canonical `session-{date}-{uuid8}.{contributor}` string + `kind` (`user`|`agent`). This is who/when/where in one string; never stamp a bare label.

A change-lug is a **normal lug** — no special type. Its completeness convention: `source_spoke`, `target_spoke`, `scope` (`local`|`cross_spoke`), `reason`, `change_summary`, `files_changed`, `commit`, `authored_by`, `authored_kind`.

---

## How to receive a change-lug

At wakeup (inbox-first), if `WAI-Spoke/lugs/incoming/` contains a change-lug (a lug with `change_summary` + `files_changed` + `source_spoke`):

1. Read the account: `reason`, `change_summary`, `files_changed`, `commit`, `authored_by`.
2. Review the change (inspect the named commit/files).
3. **Incorporate per YOUR spoke's own policies** — add tests, update docs, run gates as *your* standards require. Nothing is imposed from outside.
4. If accepted: mark handled, move to `processed/`. If rejected: emit a **counter change-lug** back to the `source_spoke` explaining why.

You own maintenance of a change once you incorporate it.

---

## Cross-spoke sovereignty (still holds)

Never write, edit, or delete files in another spoke's tree directly. A cross-spoke change travels **only** as a change-lug delivered to that spoke's `incoming/`. Look up the target path via `hub-registry.json` → `wheels[]` (match `wheel_id`/`spoke_id`) → `{path}/WAI-Spoke/lugs/incoming/`. (Spec: `spec-cross-spoke-sovereignty-v1`.)

---

## When it IS a teaching instead

If your change introduces a **new pattern the whole fleet should adopt**, or **retires** a named feature/behavior/doctrine, author a teaching (run `generate-teaching`) and post it to the Hub `teaching_repo` — that is a separate concern from change-lugs and is *required* for retirements (no silent retirements).

---

## References

- `tools/write_change_receipt.py` — emit complete change-lugs
- `tools/lug_utils.py::resolve_attribution` — canonical who/when/where attribution
- `spec-cross-spoke-sovereignty-v1` — never write a foreign tree; deliver lugs
- `generate-teaching` — the separate teaching channel (Hub `teaching_repo`)
- CLAUDE.md anti-patterns: "Blueprint contribution is open to all spokes (curator model)" and "Changes travel as complete lugs; teachings are a separate concern"
