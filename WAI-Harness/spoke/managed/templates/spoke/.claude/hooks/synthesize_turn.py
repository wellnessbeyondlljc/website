"""Synthesize a baseline track entry from the Claude Code transcript.

Safety net for the WAI Track ledger: when the model does not write
track-buffer.json for a turn, this reconstructs a faithful turn entry directly
from the transcript so no turn is ever lost. The model-authored buffer remains
the preferred ("rich") layer; this is the guaranteed floor beneath it.

Live (Stop hook):
    synthesize_turn.py <state_path> <transcript_path> <project_dir> <buffer_was_present>
      - <buffer_was_present> "1": the Stop hook already flushed a rich entry this
        turn, so we only advance the cursor (no double-write). "0": synthesize.
      - Cursor (WAI-Spoke/runtime/track-cursor.json) stores the last transcript
        uuid and last git SHA accounted for, so turns are never double-written or missed.

Backfill (one-shot recovery of a whole session):
    synthesize_turn.py --all <state_path> <transcript_path> <project_dir>
      - Reconstructs every genuine turn not already present (dedup by user_uuid).

Turn boundary: a genuine user turn is a transcript entry with
promptSource == "typed". This is precise — it ignores tool-results and
hook-injected system-reminders (validated: 8 typed prompts matched 8 real turns
exactly against a real transcript; 94 non-typed entries were all noise).

Best-effort: every failure is swallowed silently; track must never break a
session. The only way a turn is lost is a hard crash of this script itself.

Harness-mode-aware: the calling Stop hook (stop-track-flush.sh) resolves the active
v3/v4 data tree via harness_mode.sh and exports WAI_TRACK_PATH / WAI_RUNTIME_DIR /
WAI_BASE_DIR. The track, cursor, provider_usage, session-guard, and autosave all write
under that resolved tree (WAI-Spoke/ in v3, WAI-Harness/spoke/local/ in v4). When the
env is unset (direct invocation) every helper falls back to the legacy v3 layout.

Embedded enrichment (opt-in, WAI_TRACK_ENRICH=1):
    When WAI_TRACK_ENRICH=1 is set, each turn entry is enriched with `insight`
    (a dense session-aware paragraph) and `open` (unresolved user-requested work)
    via a gated embedded `claude --print` call using the enrichment addendum from
    the spoke's reference dir. The enrichment is a single-writer RMW applied before
    the entry is appended to track.jsonl, so the CSRP lane heartbeat is never raced.
    The addendum is authored in track-prompt-lab and distributed via
    track_prompt_publish.py -> track_prompt_spoke_sync.py (fleet-wide).
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path


_ADDENDUM_FILENAME = "track-prompt-enrichment-addendum.md"


def _find_addendum(project_dir: str) -> "Path | None":
    """Locate the enrichment addendum file. Checks harness-resolved dirs first (v4),
    then v3 fallback. Returns None if not found."""
    base = os.environ.get("WAI_BASE_DIR", "")
    candidates = []
    if base:
        candidates.append(Path(base) / "reference" / _ADDENDUM_FILENAME)
    root = Path(project_dir)
    candidates.append(root / "WAI-Harness" / "spoke" / "local" / "reference" / _ADDENDUM_FILENAME)
    candidates.append(root / "WAI-Spoke" / "reference" / _ADDENDUM_FILENAME)
    for c in candidates:
        if c.exists():
            return c
    return None


def _load_initiative_index(project_dir: str) -> list:
    """Load a compact [{id, label}] list from the spoke's initiative index, or []."""
    base = os.environ.get("WAI_BASE_DIR", "")
    candidates = []
    if base:
        candidates.append(Path(base) / "initiatives" / "index.json")
    root = Path(project_dir)
    candidates.append(root / "WAI-Harness" / "spoke" / "local" / "initiatives" / "index.json")
    candidates.append(root / "WAI-Spoke" / "initiatives" / "index.json")
    for c in candidates:
        if c.exists():
            try:
                raw = json.loads(c.read_text())
                items = raw.get("initiatives", raw) if isinstance(raw, dict) else raw
                return [
                    {"id": i.get("id"), "label": i.get("label")}
                    for i in (items if isinstance(items, list) else [])
                    if isinstance(i, dict)
                ]
            except Exception:
                pass
    return []


def _enrich_turn(track_path: "Path", project_dir: str, turn_entry: dict) -> dict:
    """Enrich a turn entry with `insight` + `open` via an embedded claude --print call.

    Gated to WAI_TRACK_ENRICH=1 — off by default so interactive Stop-hook fires never
    spawn a per-turn claude subprocess. Ozi or other headless callers set this to activate.
    Returns a dict with `insight` and/or `open` keys, or {} on any failure.

    Single-writer contract: the caller must merge the returned fields INTO the entry
    BEFORE writing to track.jsonl. This function is read-only (never writes the track).
    """
    if os.environ.get("WAI_TRACK_ENRICH") != "1":
        return {}
    try:
        addendum_path = _find_addendum(project_dir)
        if addendum_path is None:
            return {}

        addendum = addendum_path.read_text(encoding="utf-8")

        # Last 20 turn entries as session context (bound cost).
        session_history: list = []
        try:
            all_rows = _load_jsonl(track_path)
            session_history = [r for r in all_rows if r.get("event") == "turn"][-20:]
        except Exception:
            pass

        initiative_index = _load_initiative_index(project_dir)

        context = {
            "session_history": session_history,
            "current_turn": turn_entry,
            "initiative_index": initiative_index,
        }
        prompt = addendum + "\n\n--- CONTEXT:\n" + json.dumps(context, separators=(",", ":"))

        result = subprocess.run(
            ["claude", "--print", "--no-interactive", prompt],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=project_dir,
        )
        if result.returncode != 0:
            return {}

        output = result.stdout.strip()
        start = output.find("{")
        end = output.rfind("}") + 1
        if start < 0 or end <= start:
            return {}

        enrichment = json.loads(output[start:end])
        out: dict = {}
        if enrichment.get("insight"):
            out["insight"] = str(enrichment["insight"])
        if enrichment.get("open") is not None:
            out["open"] = enrichment["open"]
        return out
    except Exception:
        return {}


def _apply_enrichment(entry: dict, enrichment: dict) -> None:
    """Merge enrichment fields into entry, only filling missing/empty values."""
    for key in ("insight", "open"):
        if key in enrichment and not entry.get(key):
            entry[key] = enrichment[key]


def _runtime_dir(project_dir):
    """Harness-resolved runtime/ dir (env) or legacy v3 WAI-Spoke/runtime.
    Shared across lanes — provider_usage.jsonl (append-only telemetry) lives here."""
    d = os.environ.get("WAI_RUNTIME_DIR", "")
    return Path(d) if d else Path(project_dir) / "WAI-Spoke" / "runtime"


def _lane_dir(project_dir):
    """Per-session-lane private runtime (env WAI_LANE_DIR), set by the Stop hook
    when session lanes are active. Holds this session's own cursor/guard/autosave so
    concurrent sessions never share per-turn state. Falls back to the shared runtime
    dir for single-session / direct-invocation."""
    d = os.environ.get("WAI_LANE_DIR", "")
    return Path(d) if d else _runtime_dir(project_dir)


def _base_dir(project_dir):
    """Harness-resolved data base (env) or legacy v3 WAI-Spoke."""
    d = os.environ.get("WAI_BASE_DIR", "")
    return Path(d) if d else Path(project_dir) / "WAI-Spoke"


def _load_jsonl(path):
    rows = []
    try:
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return rows


def _is_typed_user(entry):
    """Genuine user turn boundary: type==user AND promptSource=='typed'."""
    return entry.get("type") == "user" and entry.get("promptSource") == "typed"


def _is_sdk_user(entry):
    """Headless turn boundary: a user entry from an SDK / headless invocation
    (promptSource=='sdk'). Herald responders and any `claude -p` one-shot land here."""
    return entry.get("type") == "user" and entry.get("promptSource") == "sdk"


def _session_entrypoint(rows):
    """The session's entrypoint marker ('sdk-cli', 'cli', ...) — first non-empty wins."""
    for e in rows:
        ep = e.get("entrypoint")
        if ep:
            return ep
    return ""


def _is_headless_session(rows):
    """True when the session was launched headless (SDK / `claude -p`), never as an
    interactive TTY. Discriminator: an 'sdk*' entrypoint is present and no 'cli'
    entrypoint is. These sessions have no typed turns, so without a dedicated record
    they leave a 0-byte phantom track that later reads as INTERRUPTED."""
    eps = {e.get("entrypoint") for e in rows if e.get("entrypoint")}
    if not eps:
        return False
    if "cli" in eps:
        return False
    return any(ep and ep.startswith("sdk") for ep in eps)


def _sdk_initiator(user_text):
    """Best-effort label for WHAT headless tool initiated the session, parsed from the
    first sdk prompt. Recognizes known callers (herald); else a slugged lead token.
    This is the provenance handle that lets a headless run's changes trace back to a
    record (every session must minimally record who called it)."""
    head = (user_text or "").strip()
    low = head.lower()
    for known in ("herald", "expediter", "autopilot", "tender", "ozi"):
        if known in low[:160]:
            return known
    m = re.match(r"\s*\[?\s*([A-Za-z][\w\- ]{2,40})", head)
    if m:
        return re.sub(r"\s+", "-", m.group(1).strip().lower())
    return "sdk"


def _text_of(content):
    """Flatten message.content (str or list of blocks) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "text"]
        return "\n".join(p for p in parts if p)
    return ""


def _build_turn(rows, start_idx, end_idx, turn_no):
    """Full-fidelity baseline entry for rows[start_idx:end_idx] (no truncation)."""
    user = rows[start_idx]
    user_text = _text_of(user.get("message", {}).get("content"))

    assistant_texts, tools, files = [], {}, []
    last_assistant_uuid, last_ts = "", user.get("timestamp", "")
    model = None
    in_tok = out_tok = cache_read = cache_create = 0

    for entry in rows[start_idx + 1:end_idx]:
        if entry.get("type") != "assistant":
            continue
        last_assistant_uuid = entry.get("uuid", last_assistant_uuid)
        last_ts = entry.get("timestamp", last_ts)
        msg = entry.get("message", {})
        if not model and msg.get("model"):
            model = msg["model"]
        usage = msg.get("usage", {})
        in_tok += usage.get("input_tokens", 0)
        out_tok += usage.get("output_tokens", 0)
        cache_read += usage.get("cache_read_input_tokens", 0)
        cache_create += usage.get("cache_creation_input_tokens", 0)
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue
        for blk in content:
            if not isinstance(blk, dict):
                continue
            if blk.get("type") == "text" and blk.get("text", "").strip():
                assistant_texts.append(blk["text"])
            elif blk.get("type") == "tool_use":
                name = blk.get("name", "?")
                tools[name] = tools.get(name, 0) + 1
                inp = blk.get("input", {})
                if isinstance(inp, dict):
                    fp = inp.get("file_path") or inp.get("path")
                    if fp and fp not in files:
                        files.append(fp)

    return {
        "event": "turn",
        "turn": turn_no,
        "source": "transcript-synth",
        "synthesized": True,
        "completed": True,
        "session_id": user.get("sessionId", ""),
        "user_uuid": user.get("uuid", ""),
        "assistant_uuid": last_assistant_uuid,
        "user_ts": user.get("timestamp", ""),
        "ts": last_ts,
        "git_branch": user.get("gitBranch", ""),
        "user_intent": user_text,
        "assistant_text": "\n\n".join(assistant_texts),
        "tools_used": [{"name": k, "count": v} for k, v in tools.items()],
        "files_touched": files,
        "model": model,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cache_read_tokens": cache_read,
        "cache_creation_tokens": cache_create,
    }


# Word-boundary patterns (NOT naive substrings). Substring matching caused phantom
# corrections: a pasted prompt containing "incorrect_predictions" matched "incorrect",
# "info." matched "no.", "whenever" matched "never". \b anchors fix all three classes.
_CORRECTION_RE = re.compile(
    r"(?<!\w)(?:"
    r"no[,.]|don'?t|stop\b|that'?s wrong|thats wrong|revert\b|actually[,.]|"
    r"instead[,.]|not like that|you should not|please don'?t|never\b|avoid\b|"
    r"that'?s not|incorrect\b|wrong approach|undo\b"
    r")",
    re.I,
)
# Scan only the conversational LEAD, not the whole message: a user who pastes a code
# block / prompt / doc after a benign request must not trip a correction on words buried
# in the pasted bulk. ~400 chars covers a normal correction sentence.
_CORRECTION_HEAD = 400


def _detect_correction(user_text, prior_assistant_text):
    """Return a correction descriptor if this user turn corrects the prior response."""
    if not user_text or not prior_assistant_text:
        return None
    head = user_text[:_CORRECTION_HEAD]
    matched = list(dict.fromkeys(m.strip() for m in _CORRECTION_RE.findall(head.lower())))
    if not matched:
        return None
    confidence = round(min(0.3 + 0.15 * len(matched), 0.85), 2)
    return {
        "trigger": head[:300],
        "prior_action": prior_assistant_text[:300],
        "keywords": matched[:5],
        "confidence": confidence,
    }


def _append_provider_usage(project_dir, entry):
    """Append a per-turn provider usage row for Navigator consumption."""
    try:
        usage_path = _runtime_dir(project_dir) / "provider_usage.jsonl"
        row = {
            "session_id": entry.get("session_id", ""),
            "ts": entry.get("ts", ""),
            "model": entry.get("model"),
            "input_tokens": entry.get("input_tokens", 0),
            "output_tokens": entry.get("output_tokens", 0),
            "cache_read_tokens": entry.get("cache_read_tokens", 0),
            "cache_creation_tokens": entry.get("cache_creation_tokens", 0),
            "session_type": "interactive",
        }
        with usage_path.open("a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass


def _git_info(project_dir, last_sha):
    """Get objective git fields since last_sha. Returns empty lists on failure."""
    if not last_sha:
        return {"commits_since_last": [], "files_changed": []}
    try:
        curr_sha = subprocess.run(
            ["git", "-C", project_dir, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        if not curr_sha or curr_sha == last_sha:
            return {"commits_since_last": [], "files_changed": []}

        log_out = subprocess.run(
            ["git", "-C", project_dir, "log",
             f"{last_sha}..{curr_sha}", "--pretty=format:%H|%s"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        commits = []
        for line in log_out.splitlines():
            if "|" in line:
                sha, _, subj = line.partition("|")
                commits.append({"sha": sha.strip(), "subject": subj.strip()})

        diff_out = subprocess.run(
            ["git", "-C", project_dir, "diff", "--name-only", last_sha, curr_sha],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        files = [f for f in diff_out.splitlines() if f]

        return {"commits_since_last": commits, "files_changed": files}
    except Exception:
        return {"commits_since_last": [], "files_changed": []}


def _get_head_sha(project_dir):
    """Return current HEAD SHA or empty string on failure."""
    try:
        return subprocess.run(
            ["git", "-C", project_dir, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        return ""


def _write_autosave(project_dir, turn_no, ts, focus):
    """Write rolling autosave checkpoint; keep last 3."""
    try:
        d = _lane_dir(project_dir) / "autosave"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"turn-{turn_no}.json").write_text(json.dumps({
            "turn": turn_no,
            "ts": ts,
            "focus": (focus or "")[:120],
            "completed": True,
            "state": {},
        }))
        checkpoints = sorted(
            d.glob("turn-*.json"),
            key=lambda p: int(p.stem.split("-")[1]) if p.stem.split("-")[1].isdigit() else 0,
        )
        for f in checkpoints[:-3]:
            try:
                f.unlink()
            except Exception:
                pass
    except Exception:
        pass


def _update_session_guard(project_dir, turn_no):
    """Write turn_count to session-guard.json."""
    try:
        guard = _lane_dir(project_dir) / "session-guard.json"
        data = {}
        if guard.exists():
            try:
                data = json.loads(guard.read_text())
            except Exception:
                data = {}
        data["turn_count"] = turn_no
        guard.parent.mkdir(parents=True, exist_ok=True)
        guard.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def _track_path(state_path, project_dir):
    # Harness-resolved track path (env, set by stop-track-flush.sh) wins.
    env = os.environ.get("WAI_TRACK_PATH", "")
    if env:
        p = Path(env)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    state = json.loads(Path(state_path).read_text())
    rel = state.get("_session_state", {}).get("track_path", "")
    if not rel:
        return None
    p = Path(project_dir) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _existing_turn_count(track_path):
    return sum(1 for r in _load_jsonl(track_path) if r.get("event") == "turn")


def _session_closed(track_path):
    """True if the track's last entry is a terminal closeout — the session is
    closing. The Stop hook fires after the closeout response too, so without this
    guard the synthesizer would append a turn AFTER the closeout, making the next
    wakeup read the session as INTERRUPTED. Closeout must stay the terminal line."""
    rows = _load_jsonl(track_path)
    return bool(rows) and rows[-1].get("event") == "closeout"


def _has_meaning(entry):
    return bool(entry["user_intent"] or entry["assistant_text"] or entry["tools_used"])


def backfill(state_path, transcript_path, project_dir):
    """Reconstruct every genuine turn not already recorded (dedup by user_uuid)."""
    track = _track_path(state_path, project_dir)
    if track is None:
        return
    rows = _load_jsonl(transcript_path)
    if not rows:
        return
    starts = [i for i, e in enumerate(rows) if _is_typed_user(e)]
    if not starts:
        return
    bounds = starts + [len(rows)]
    seen = {r.get("user_uuid") for r in _load_jsonl(track) if r.get("user_uuid")}
    turn_no = _existing_turn_count(track)
    out = []
    for ci, si in enumerate(starts):
        if rows[si].get("uuid") in seen:
            continue
        turn_no += 1
        out.append(_build_turn(rows, bounds[ci], bounds[ci + 1], turn_no))
    out = [e for e in out if _has_meaning(e)]
    if out:
        with track.open("a") as f:
            for e in out:
                f.write(json.dumps(e) + "\n")


def live(state_path, transcript_path, project_dir, buffer_was_present):
    """Synthesize the just-completed turn (unless a rich buffer was flushed)."""
    track = _track_path(state_path, project_dir)
    if track is None:
        return
    # Session is closing — do not append turns after the terminal closeout entry.
    if _session_closed(track):
        return
    rows = _load_jsonl(transcript_path)
    if not rows:
        return

    cursor_path = _lane_dir(project_dir) / "track-cursor.json"
    last_uuid = ""
    last_sha = ""
    try:
        cursor_data = json.loads(cursor_path.read_text())
        last_uuid = cursor_data.get("last_uuid", "")
        last_sha = cursor_data.get("last_sha", "")
    except Exception:
        pass

    # Window = entries after the cursor. If cursor is unknown/stale, anchor to the
    # last typed prompt so we never backfill the whole transcript on first run.
    start_idx = 0
    if last_uuid:
        for i, e in enumerate(rows):
            if e.get("uuid") == last_uuid:
                start_idx = i + 1
                break
    if not last_uuid or start_idx == 0:
        typed = [i for i, e in enumerate(rows) if _is_typed_user(e)]
        start_idx = typed[-1] if typed else 0

    window = rows[start_idx:]
    if not window:
        return

    # Always advance the cursor and store current HEAD SHA.
    newest_uuid = next((e["uuid"] for e in reversed(window) if e.get("uuid")), "")
    head_sha = _get_head_sha(project_dir)
    try:
        cursor_path.parent.mkdir(parents=True, exist_ok=True)
        cursor_path.write_text(json.dumps({
            "last_uuid": newest_uuid,
            "last_sha": head_sha,
        }))
    except Exception:
        pass

    # Rich entry already written by the model this turn — augment it with
    # conversation content + token data from the transcript, then write
    # provider_usage, autosave, and session guard.
    if buffer_was_present:
        typed_in_window = [i for i, e in enumerate(window) if _is_typed_user(e)]
        if typed_in_window:
            s = typed_in_window[-1]
            synth = _build_turn(window, s, len(window), 0)
            try:
                lines = [ln for ln in track.read_text().splitlines() if ln.strip()]
                if lines:
                    last = json.loads(lines[-1])
                    if last.get("event") == "turn":
                        for field in ("user_intent", "assistant_text", "tools_used", "files_touched"):
                            if not last.get(field):
                                last[field] = synth.get(field) or ([] if field in ("tools_used", "files_touched") else "")
                        for field in ("model", "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"):
                            if not last.get(field):
                                last[field] = synth.get(field)
                        # Enrich model-authored entry with insight/open if missing.
                        _apply_enrichment(last, _enrich_turn(track, project_dir, last))
                        lines[-1] = json.dumps(last)
                        track.write_text("\n".join(lines) + "\n")
                        _append_provider_usage(project_dir, synth)
            except Exception:
                pass
        turn_no = _existing_turn_count(track)
        entries = _load_jsonl(track)
        last_entry = entries[-1] if entries else {}
        _write_autosave(
            project_dir, turn_no,
            last_entry.get("ts", ""),
            last_entry.get("user_intent") or last_entry.get("focus", ""),
        )
        _update_session_guard(project_dir, turn_no)
        return

    # No buffer: synthesize EVERY genuine typed turn not already in the track (dedup by
    # user_uuid) over the FULL transcript — not just the post-cursor window. Self-healing:
    # a missed Stop fire (or a late first fire that skipped earlier turns) never permanently
    # loses a turn; the next fire recovers the whole backlog. Idempotent via uuid dedup. The
    # cursor above stays a cheap fast-path hint but is no longer the correctness guard — uuid
    # dedup is. (bug-live-track-capture-nonfunctional-20260619: Layer-2 floor must never depend
    # on the model writing a buffer, and must recover any turns a missed fire left behind.)
    starts = [i for i, e in enumerate(rows) if _is_typed_user(e)]
    headless = False
    if not starts:
        # No typed turns. If this is a headless (SDK / `claude -p`) session, capture its
        # turn(s) as an sdk_session record so the track is never a 0-byte phantom AND the
        # run's changes trace back to the initiating tool. Interactive sessions with no
        # typed turn (truly nothing to record) still return.
        if _is_headless_session(rows):
            starts = [i for i, e in enumerate(rows) if _is_sdk_user(e)]
            headless = True
        if not starts:
            return
    entrypoint = _session_entrypoint(rows) if headless else ""
    bounds = starts + [len(rows)]
    seen = {r.get("user_uuid") for r in _load_jsonl(track) if r.get("user_uuid")}
    turn_no = _existing_turn_count(track)
    prior_entries = _load_jsonl(track)
    prior_assistant = prior_entries[-1].get("assistant_text", "") if prior_entries else ""
    to_write = []
    for ci, si in enumerate(starts):
        if rows[si].get("uuid") in seen:
            continue
        turn_no += 1
        entry = _build_turn(rows, bounds[ci], bounds[ci + 1], turn_no)
        if not _has_meaning(entry):
            turn_no -= 1
            continue
        if headless:
            # Tag as a headless record with provenance. event != "turn" so wakeup's
            # INTERRUPTED-detection treats it as terminal (HEADLESS), not a crash.
            entry["event"] = "sdk_session"
            entry["source"] = "sdk-synth"
            entry["headless"] = True
            entry["entrypoint"] = entrypoint
            entry["initiator"] = _sdk_initiator(entry.get("user_intent", ""))
            correction = None
        else:
            correction = _detect_correction(entry.get("user_intent", ""), prior_assistant)
        to_write.append((entry, correction))
        prior_assistant = entry.get("assistant_text", "") or prior_assistant
    if not to_write:
        return

    # Git enrichment only on the newest entry (bounded cost; older turns' spans are noise).
    # Skip for headless records: the repo delta since the cursor is misleading there (it is
    # NOT what the one-shot did) — files_touched/tools_used are the accurate provenance of
    # what a headless run changed.
    if not headless:
        git = _git_info(project_dir, last_sha)
        to_write[-1][0]["commits_since_last"] = git["commits_since_last"]
        to_write[-1][0]["files_changed"] = git["files_changed"]

    # Embedded enrichment (WAI_TRACK_ENRICH=1): patch insight+open onto each entry
    # before writing. Only the most recent turn of a run is enriched (bounded cost).
    # Non-headless session turns with no existing insight are the primary target.
    if not headless and to_write:
        last_entry = to_write[-1][0]
        _apply_enrichment(last_entry, _enrich_turn(track, project_dir, last_entry))

    with track.open("a") as f:
        for entry, correction in to_write:
            f.write(json.dumps(entry) + "\n")
            if correction:
                f.write(json.dumps({
                    "event": "correction",
                    "turn": entry["turn"],
                    "session_id": entry.get("session_id", ""),
                    "ts": entry.get("ts", ""),
                    **correction,
                }) + "\n")

    newest = to_write[-1][0]
    _append_provider_usage(project_dir, newest)
    _write_autosave(project_dir, newest["turn"], newest.get("ts", ""), newest.get("user_intent", ""))
    _update_session_guard(project_dir, newest["turn"])


def main():
    args = sys.argv[1:]
    if not args:
        return
    try:
        if args[0] == "--all":
            if len(args) >= 4:
                backfill(args[1], args[2], args[3])
            return
        if len(args) >= 4:
            live(args[0], args[1], args[2], args[3] == "1")
    except Exception:
        pass  # track is best-effort; never break the session


if __name__ == "__main__":
    main()
