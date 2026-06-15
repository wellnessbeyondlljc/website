# WAI Wakeup Protocol — Reference (Fast Path)

> Full reference: load `wai-reference.md` for complete scripts, verbose specs, and signal lifecycle detail.

**Most-needed sections from the wakeup reference.**

---

## Track Integrity Check (Step 3b)

```bash
LAST_TRACK="WAI-Spoke/sessions/$(ls -1t WAI-Spoke/sessions/ | sed -n '2p')/track.jsonl"
if [ -f "$LAST_TRACK" ]; then
    LAST_LINE=$(tail -1 "$LAST_TRACK")
    if echo "$LAST_LINE" | jq -e '.completed == true or .event == "closeout"' >/dev/null 2>&1; then
        STATUS="CLEAN"
    else
        STATUS="INTERRUPTED"
    fi
else
    STATUS="FIRST_SESSION"
fi
```

**INTERRUPTED:** Recovery is handled by `wai-enter.sh` before launch — no in-session action needed.

---

## Lug Folder Structure (Step 4)

```
WAI-Spoke/lugs/bytype/
  epic/{open,in_progress,completed}/
  task/{open,in_progress,completed}/
  feature/{open,in_progress,completed}/
  bug/{open,in_progress,completed}/
  implementation/{in_progress,completed}/
  session-summary/
  other/{open,completed}/
```

---

## Wakeup Fast Path Decision

| Condition | Path |
|-----------|------|
| `<wai-session-init>` present AND brief is FRESH | **FAST PATH** — 0 tool calls, display immediately |
| Brief is STALE or absent | **FULL PROTOCOL** — load `wai.md` Step 3+ |

---

## Session Track Ledger Format

```
| {n} | {HH:MM UTC} | {event} | {notes} |
```

First row header: `| # | Time | Event | Notes |`
Append one row per turn.
