# WAI Wakeup Protocol — Fast Path

> Full protocol: load `wai.md` when brief is STALE, session-init is absent, or SESSION_INTENT=full. Full path uses 4-6 tool calls (~60s).

**0 tool calls — FRESH brief only.** Use when `<wai-session-init>` is in context AND brief is marked FRESH.

---

## Pre-Check

Is `<wai-session-init>` in context AND brief is `FRESH`?
- **YES → use this file (0 tool calls)**
- **NO → load `wai.md` for full protocol**

---

## Step 0 — Intent Check

Scan `<wai-session-init>` CONTEXT HEALTH for `Intent:` line.
- Found → extract `SESSION_INTENT`, run Step 0.5, then jump to Step 2b after banner
- Absent → run Step 0.5, then proceed Steps 1–4 normally

---

## Step 0.5 — Priority Gate (mandatory, even on fast path)

If a hub base is reachable, OR `TEACH_NEW > 0`, OR `Incoming: N lug(s) pending triage`:
execute **A → B → C in order** from `wai.md` Step 0.5 silently, **before** the banner, intent router, or savepoint intercept:

- **A — Harness base adoption (FIRST, hard gate):** if `_harness.base_version` is behind the hub base (or absent), run the adoption kit once and emit an adoption bolt. Teachings/patches do NOT apply until base is current.
- **B — Patch + teaching adoption** (only after base is current).
- **C — Incoming lug triage.**

Report: `Step 0.5A: base {v} | Step 0.5B: N adopted | Step 0.5C: N triaged`. Then continue.

(If nothing is pending and base is current, this step is a silent no-op.)

---

## Step 1 — Interrupted Session

If `Prev session: INTERRUPTED` in CONTEXT HEALTH: note `⚠ Prev session interrupted — recovery prompt shown pre-launch`. No action needed.

---

## Step 2 — Display Banner

```
┌─ WAI WAKEUP Session-{N} [{session_name}] {today_date}
│  Project: {name} v{version}
│  Active: {epics_open} open, {epics_ip} ip | {other_open} other | {signals} signals
│  Queue: {ready} ready | {refinement} refinement
│  {If _savepoint.status == "pending": ⚑ Savepoint: [lug_id] | Done: [work_done] | Next: [resume_note]}
│  Intent: {intent} — {intent_label}  (or: Vibe: none | Context: unknown)
│  {If TEACHINGS New > 0: Teachings: N pending}
│  {If HUB SIGNALS > 0: Hub signals: N framework}
│  {If Tool audit due: ⚠ Tool audit due}
│  {If Hook drift: ⚠ Hook drift: N stale}
│  {If Historian advice: Historian: {first bullet}}
│  {Active feedback: top-3 from MEMORY.md}
│  Next: {first item from NEXT ACTIONS}
└─ Ready to work.
```

---

## Step 2b — Intent Router

| Intent | Action |
|--------|--------|
| `savepoint` | Read savepoint lug + track (max 3 calls). Resume or abandon. |
| `implement` | Read WAI-State.json (1 call). Show top-3 ready lugs by ROI. |
| `refinement` | Read WAI-State.json (1 call). Show needs_refinement items. |
| `teachings` | List seed/ingest/ (1 call). Show pending count. |
| `closeout` | Display reminder. Invoke `/wai-closeout`. |
| `explore` | Skip router, proceed normally. |
| `full` | Abandon savepoints. Load `wai.md` full protocol. |

After routing → proceed directly to work. Do NOT ask for vibe.

---

## Step 3 — Vibe (if no intent)

Ask: `Vibe? (build / fix / think / grind / ship / refine) [skip]`
Write to `WAI-State.json._session_state.current_vibe`.

---

## Step 4 — Work Queue

If `_work_queue.items` has ≥1 ready item: display top-3 by ROI.
