#!/usr/bin/env python3
"""
scout_executor.py — Wayfinder SOP-4 runner.

Loads scout job definitions from WAI-Spoke/scouts/{scope}/ready/, gathers inputs
per input_shape, renders prompt_template, routes through a provider adapter
(default: NVIDIA), runs verification_gate, emits activity_events, and files bug
lugs on failure with SOP-5 repeat-fire dedup.

Lives in tools/ alongside wayfinder_cycle_close.py and emit_activity_event.py.
"""

from __future__ import annotations

import argparse
import datetime
import glob
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import wai_paths  # noqa: E402  harness-mode root resolver

from _schema_validate import validate as _validate_scout  # noqa: E402

# Data dirs (scouts, bug lugs) live in the spoke's LOCAL plane, resolved base-aware from
# the spoke root — NOT under _REPO_ROOT (the managed install dir). PRE-FIX they pointed at
# managed/WAI-Spoke/... which does not exist on v4, so `--all-ready` found 0 scouts and the
# wayfinder runner silently did nothing (impl-fix-p1-silent-dead-v4-paths-v1). SCHEMA_PATH is
# a managed reference that ships under managed/reference/ (resolved via _REPO_ROOT).
def _lugs_base(spoke_root) -> Path:
    """The dir whose lugs/scouts live for this spoke, base-aware (v4 local, else v3)."""
    try:
        base, mode = wai_paths.resolve_wai_root(str(spoke_root))
        if base and mode != "none":
            return Path(base)
    except Exception:
        pass
    return Path(spoke_root) / "WAI-Spoke"


_SPOKE_ROOT = Path(os.environ.get("WAI_SPOKE_ROOT") or os.getcwd())
_LOCAL = _lugs_base(_SPOKE_ROOT)
SCOUTS_SPOKE_READY = _LOCAL / "scouts/spoke_local/ready"
SCOUTS_HUB_READY = _LOCAL / "scouts/hub_universal/ready"
SCHEMA_PATH = _REPO_ROOT / "reference/scout-job.schema.json"
BUG_LUG_DIR = _LOCAL / "lugs/bytype/bug/open"
EMIT_EVENT_CLI = _HERE / "emit_activity_event.py"
ADAPTERS_DIR = _REPO_ROOT / "hub/WAI-Hub/advisors/navigator/adapters"

DEFAULT_MODEL = "meta/llama-3.3-70b-instruct"
DEFAULT_PROVIDER = "nvidia"
DEFAULT_BUDGET = 8
RETRY_BACKOFFS = [2, 8, 32]

# Per-input_shape hardcoded source recipes, keyed by scout id (until
# feature-scout-input-source-schema-v1 lands a first-class field). Each entry
# returns the input string from a callable taking (spoke_root: Path) -> str.
_INPUT_RECIPES: dict[str, callable] = {}


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _utc_compact() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")


def _truncate(s: str, cap: int = 8000) -> str:
    if len(s) <= cap:
        return s
    return s[:cap] + f"\n... [truncated {len(s) - cap} bytes]"


# ── Loading ──────────────────────────────────────────────────────────


def load_scout(id_or_path: str) -> tuple[dict, Path]:
    """Resolve a scout by id (searches ready dirs) or by absolute path."""
    p = Path(id_or_path)
    if p.is_file():
        path = p
    else:
        candidates = list(SCOUTS_SPOKE_READY.glob(f"{id_or_path}.json")) + list(
            SCOUTS_HUB_READY.glob(f"{id_or_path}.json")
        )
        if not candidates:
            raise SystemExit(f"scout not found: {id_or_path}")
        path = candidates[0]
    scout = json.loads(path.read_text())
    ok, errs = _validate_scout(scout, str(SCHEMA_PATH))
    if not ok:
        msg = "; ".join(errs[:5])
        raise SystemExit(f"scout {path.name} fails schema: {msg}")
    return scout, path


def list_ready_scouts() -> list[Path]:
    """All scout files in ready dirs, sorted by id."""
    paths = sorted(SCOUTS_SPOKE_READY.glob("*.json")) + sorted(SCOUTS_HUB_READY.glob("*.json"))
    return paths


# ── Input gathering ──────────────────────────────────────────────────


def _gather_lug_list(spoke_root: Path) -> str:
    """Serialize a snapshot of open + in_progress lugs (cap 50, 8KB total)."""
    _b = _lugs_base(spoke_root)
    lug_paths = sorted(_b.glob("lugs/bytype/*/open/*.json"))
    lug_paths += sorted(_b.glob("lugs/bytype/*/in_progress/*.json"))
    lug_paths = lug_paths[:50]
    rows = []
    for p in lug_paths:
        try:
            lug = json.loads(p.read_text())
        except Exception:
            continue
        rows.append({
            "id": lug.get("id"),
            "type": lug.get("type"),
            "status": lug.get("status"),
            "title": (lug.get("title") or "")[:120],
            "perceive": bool(lug.get("perceive")),
            "execute": bool(lug.get("execute")),
            "verify": bool(lug.get("verify")),
        })
    return _truncate(json.dumps(rows, indent=2))


def _gather_lug_filter(spoke_root: Path, spec: dict) -> str:
    """Gather lugs matching filter spec. Includes updated_at/created_at for staleness checks."""
    statuses = spec.get("statuses") or ["open", "in_progress"]
    cap = int(spec.get("cap", 50))
    lug_paths: list[Path] = []
    _b = _lugs_base(spoke_root)
    for status in statuses:
        lug_paths += sorted(_b.glob(f"lugs/bytype/*/{status}/*.json"))
    lug_paths = sorted(set(lug_paths))[:cap]
    rows = []
    for p in lug_paths:
        try:
            lug = json.loads(p.read_text())
        except Exception:
            continue
        rows.append({
            "id": lug.get("id"),
            "type": lug.get("type"),
            "status": lug.get("status"),
            "title": (lug.get("title") or "")[:120],
            "perceive": bool(lug.get("perceive")),
            "execute": bool(lug.get("execute")),
            "verify": bool(lug.get("verify")),
            "updated_at": lug.get("updated_at"),
            "created_at": lug.get("created_at"),
        })
    return _truncate(json.dumps(rows, indent=2))


def _gather_file_path_list(spoke_root: Path, glob_pat: str) -> str:
    """Return one line per matched file: 'PATH:\\n<first 2KB>\\n---\\n'."""
    paths = sorted((spoke_root / "").glob(glob_pat)) if "*" in glob_pat else [spoke_root / glob_pat]
    parts = []
    total = 0
    for p in paths:
        if not p.is_file():
            continue
        try:
            content = p.read_text(errors="replace")[:2000]
        except Exception:
            continue
        chunk = f"{p.relative_to(spoke_root)}:\n{content}\n---\n"
        if total + len(chunk) > 8000:
            parts.append(f"... [truncated, {len(paths) - len(parts)} more files]")
            break
        parts.append(chunk)
        total += len(chunk)
    return "".join(parts) if parts else "[no files matched]"


def _gather_incoming_lugs(spoke_root: Path) -> str:
    """Gather incoming lug JSON, resolving the incoming dir by harness mode.

    v3 spoke -> <root>/WAI-Spoke/lugs/incoming ; v4-only -> <root>/WAI-Harness/spoke/local/lugs/incoming.
    Output matches _gather_file_path_list (PATH:\\n<first 2KB>\\n---\\n)."""
    lugs_base = wai_paths.category(str(spoke_root), "lugs") or str(Path(spoke_root) / "WAI-Spoke" / "lugs")
    incoming = Path(lugs_base) / "incoming"
    paths = sorted(incoming.glob("*.json")) if incoming.is_dir() else []
    parts = []
    total = 0
    for p in paths:
        if not p.is_file():
            continue
        try:
            content = p.read_text(errors="replace")[:2000]
        except Exception:
            continue
        try:
            rel = p.relative_to(spoke_root)
        except ValueError:
            rel = p.name
        chunk = f"{rel}:\n{content}\n---\n"
        if total + len(chunk) > 8000:
            parts.append(f"... [truncated, {len(paths) - len(parts)} more files]")
            break
        parts.append(chunk)
        total += len(chunk)
    return "".join(parts) if parts else "[no files matched]"


def _gather_diff(spoke_root: Path, range_spec: str = "HEAD~5..HEAD") -> str:
    """git diff for range_spec, capped at 8KB."""
    try:
        out = subprocess.run(
            ["git", "-C", str(spoke_root), "diff", range_spec],
            capture_output=True, text=True, timeout=15,
        )
        return _truncate(out.stdout or "[empty diff]")
    except Exception as e:
        return f"[git diff failed: {e}]"


def _gather_log_chunk(spoke_root: Path) -> str:
    """Tail last 200 lines of WAI-Spoke/runtime/spoke-changelog.jsonl."""
    log_path = spoke_root / "WAI-Spoke/runtime/spoke-changelog.jsonl"
    if not log_path.exists():
        return "[spoke-changelog.jsonl absent]"
    lines = log_path.read_text(errors="replace").splitlines()[-200:]
    return _truncate("\n".join(lines))


def _gather_jsonl_tail(spoke_root: Path, path: str, lines: int = 200) -> str:
    """Tail last N lines of any JSONL file at the given relative path."""
    log_path = spoke_root / path
    if not log_path.exists():
        return f"[{path} absent]"
    all_lines = log_path.read_text(errors="replace").splitlines()[-lines:]
    return _truncate("\n".join(all_lines))


def _gather_json_blob(spoke_root: Path, path: str = None) -> str:
    """Read a JSON blob. Defaults to the assessor model registry when no path given."""
    p = spoke_root / path if path else spoke_root / "hub/advisors/assessor/registry/model-registry.json"
    if p.exists():
        return _truncate(p.read_text(errors="replace"))
    return f"[json_blob source '{path or 'default'}' absent]"


def _gather_text(spoke_root: Path, default_path: str = "WAI-Spoke/WAI-State.json") -> str:
    p = spoke_root / default_path
    if not p.exists():
        return f"[text source {default_path} absent]"
    return _truncate(p.read_text(errors="replace"))


# Per-scout recipes (override defaults by scout id)
_INPUT_RECIPES.update({
    "scout-archie-coding-todo-density-v1":
        lambda root: _gather_file_path_list(root, "tools/*.py"),
    "scout-archie-coding-tool-shebang-v1":
        lambda root: _gather_file_path_list(root, "tools/*.py"),
    "scout-archie-continuity-orphan-incoming-lug-v1":
        lambda root: _gather_incoming_lugs(root),
    "scout-archie-config-dispatch-script-exists-v1":
        lambda root: _gather_json_blob(root),
    "scout-archie-coding-diff-no-secret-leak-v1":
        lambda root: _gather_diff(root),
    "scout-archie-log-changelog-error-burst-v1":
        lambda root: _gather_log_chunk(root),
    "scout-archie-continuity-state-json-valid-v1":
        lambda root: _gather_text(root, "WAI-Spoke/WAI-State.json"),
})


def _gather_from_source(input_source: dict, spoke_root: Path) -> str:
    """Dispatch on input_source.type to gather input data for a scout."""
    src_type = input_source.get("type", "")
    spec = input_source.get("spec") or {}
    if src_type == "file_glob":
        pattern = spec.get("pattern", "")
        if not pattern:
            return "[file_glob: missing pattern in spec]"
        return _gather_file_path_list(spoke_root, pattern)
    if src_type == "file_path":
        path = spec.get("path", "")
        if not path:
            return "[file_path: missing path in spec]"
        return _gather_text(spoke_root, path)
    if src_type == "lug_filter":
        return _gather_lug_filter(spoke_root, spec)
    if src_type == "git_diff_range":
        return _gather_diff(spoke_root, spec.get("range", "HEAD~5..HEAD"))
    if src_type == "jsonl_tail":
        path = spec.get("path", "")
        if not path:
            return "[jsonl_tail: missing path in spec]"
        return _gather_jsonl_tail(spoke_root, path, int(spec.get("lines", 200)))
    if src_type == "json_path":
        path = spec.get("path", "")
        if not path:
            return "[json_path: missing path in spec]"
        return _gather_json_blob(spoke_root, path)
    return f"[unknown input_source.type: {src_type}]"


def gather_input(scout: dict, spoke_root: Path) -> str:
    """Dispatch on input_source field first; fall back to hardcoded recipes and shape defaults."""
    input_source = scout.get("input_source")
    if input_source:
        return _gather_from_source(input_source, spoke_root)
    # Legacy fallback: per-scout hardcoded recipes
    sid = scout.get("id", "")
    if sid in _INPUT_RECIPES:
        return _INPUT_RECIPES[sid](spoke_root)
    # Shape-level defaults
    shape = scout["input_shape"]
    if shape == "lug_list":
        return _gather_lug_list(spoke_root)
    if shape == "file_path_list":
        return _gather_file_path_list(spoke_root, "tools/*.py")
    if shape == "diff":
        return _gather_diff(spoke_root)
    if shape == "log_chunk":
        return _gather_log_chunk(spoke_root)
    if shape == "json_blob":
        return _gather_json_blob(spoke_root)
    if shape == "text":
        return _gather_text(spoke_root)
    return f"[unknown input_shape: {shape}]"


def render_prompt(scout: dict, payload: str) -> str:
    return scout["prompt_template"].replace("{input}", payload)


# ── Model call ───────────────────────────────────────────────────────


def _load_adapter(provider: str):
    """Dynamic-load the named adapter from hub/WAI-Hub/... by file path."""
    path = ADAPTERS_DIR / f"{provider}.py"
    if not path.exists():
        raise RuntimeError(f"adapter not found: {path}")
    spec = importlib.util.spec_from_file_location(f"adapter_{provider}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def call_model(prompt: str, model: str, provider: str = DEFAULT_PROVIDER) -> dict:
    """Call the provider's chat_completion with 3 retries + exponential backoff."""
    adapter = _load_adapter(provider)
    if not hasattr(adapter, "chat_completion"):
        raise RuntimeError(f"adapter {provider} has no chat_completion()")

    messages = [{"role": "user", "content": prompt}]
    last_err: Optional[Exception] = None
    for attempt, backoff in enumerate([0] + RETRY_BACKOFFS):
        if backoff:
            time.sleep(backoff)
        try:
            return adapter.chat_completion(model=model, messages=messages)
        except Exception as e:
            last_err = e
            print(f"[scout_executor] call_model attempt {attempt + 1}: {e}", file=sys.stderr)
    raise RuntimeError(f"call_model exhausted retries: {last_err}")


# ── Verification ─────────────────────────────────────────────────────


def _verify_pattern_match(spec: dict, output: str) -> tuple[bool, dict]:
    import re as _re
    pattern = spec.get("pattern", ".*")
    pass_value = spec.get("pass_value", "PASS")
    lines = [l for l in output.splitlines() if l.strip()]
    if not lines:
        return False, {"reason": "no non-empty lines in output"}
    matched = [bool(_re.match(pattern, l)) for l in lines]
    pass_lines = [l for l in lines if l.startswith(pass_value)]
    passed = all(matched) and len(pass_lines) == len(lines)
    return passed, {"lines": len(lines), "matched": sum(matched), "pass_lines": len(pass_lines)}


def _verify_presence_absence(spec: dict, output: str) -> tuple[bool, dict]:
    must_contain = spec.get("must_contain", []) or []
    must_not_contain = spec.get("must_not_contain", []) or []
    missing = [s for s in must_contain if s not in output]
    forbidden = [s for s in must_not_contain if s in output]
    passed = not missing and not forbidden
    return passed, {"missing": missing, "forbidden": forbidden}


def _verify_range_check(spec: dict, output: str) -> tuple[bool, dict]:
    import re as _re
    lo = spec.get("min", 0)
    hi = spec.get("max", 0)
    m = _re.search(r"-?\d+", output)
    if not m:
        return False, {"reason": "no integer in output"}
    val = int(m.group(0))
    passed = lo <= val <= hi
    return passed, {"value": val, "min": lo, "max": hi}


def _verify_schema_validation(spec: dict, output: str) -> tuple[bool, dict]:
    import sys as _sys
    if str(_HERE) not in _sys.path:
        _sys.path.insert(0, str(_HERE))
    from _schema_validate import validate_dict
    try:
        instance = json.loads(output)
    except json.JSONDecodeError as e:
        return False, {"reason": f"not valid JSON: {e}"}
    schema = spec.get("schema") or {}
    errs = validate_dict(instance, schema)
    return (not errs), {"errors": errs[:5]}


def run_verification(scout: dict, model_output: str) -> dict:
    gate = scout["verification_gate"]
    vtype = gate["verification_type"]
    spec = gate.get("verification_spec", {})
    score_map = gate.get("score_mapping", {"pass": 1.0, "fail": 0.0})

    if vtype == "pattern_match":
        passed, details = _verify_pattern_match(spec, model_output)
    elif vtype == "presence_absence":
        passed, details = _verify_presence_absence(spec, model_output)
    elif vtype == "range_check":
        passed, details = _verify_range_check(spec, model_output)
    elif vtype == "schema_validation":
        passed, details = _verify_schema_validation(spec, model_output)
    else:
        return {"passed": False, "score": 0.0, "details": {"reason": f"verification_type {vtype} not implemented in MVP"}}

    # Self-finding heuristics
    import re as _re
    if not passed:
        if _re.search(r"\bI (cannot|won't|can not|am unable)\b|<refusal>", model_output, _re.I):
            details["self_finding_subtype"] = "refusal"
        elif "PASS" in model_output and "FAIL" in model_output:
            details["self_finding_subtype"] = "confusion"

    return {
        "passed": passed,
        "score": float(score_map.get("pass" if passed else "fail", 0.0)),
        "details": details,
    }


# ── Activity event emission ──────────────────────────────────────────


def emit_activity_event(scout: dict, result: dict, model: str, run_meta: dict, session_id: str) -> None:
    event = {
        "event_type": "scout_run",
        "spoke_id": run_meta.get("spoke_id", ""),
        "advisor_id": scout.get("owner", ""),
        "scout_job_id": scout["id"],
        "model_used": model,
        "verification_type": scout["verification_gate"]["verification_type"],
        "passed": bool(result["passed"]),
        "score": float(result["score"]),
        "duration_ms": int(run_meta.get("duration_ms", 0)),
        "budget_consumed_tokens": int(run_meta.get("tokens_in", 0) + run_meta.get("tokens_out", 0)),
        "ts": _now_iso(),
        "session_id": session_id,
    }
    try:
        subprocess.run(
            ["python3", str(EMIT_EVENT_CLI), json.dumps(event)],
            capture_output=True, timeout=10, check=False,
        )
    except Exception as e:
        print(f"[scout_executor] activity_event emit failed: {e}", file=sys.stderr)


# ── Bug lug filing (SOP-5) ───────────────────────────────────────────


def _signal_to_priority(signal_level: str) -> str:
    return {
        "staff": "P1",
        "external_user": "P2",
        "infrastructure": "P2",
        "codebase": "P3",
    }.get(signal_level, "P3")


def _target_scope_hash(scout: dict, payload: str) -> str:
    """Stable hash of scout id + first 200 chars of input payload (dedup key)."""
    h = hashlib.sha256()
    h.update(scout["id"].encode())
    h.update(payload[:200].encode())
    return h.hexdigest()[:12]


def file_bug_lug(scout: dict, finding: dict, session_id: str, payload: str) -> Optional[str]:
    """Create-or-update a bug lug for this scout finding. Returns lug path."""
    BUG_LUG_DIR.mkdir(parents=True, exist_ok=True)
    scope_hash = _target_scope_hash(scout, payload)

    existing = None
    for p in BUG_LUG_DIR.glob("bug-scout-*.json"):
        try:
            cand = json.loads(p.read_text())
        except Exception:
            continue
        if cand.get("scout_job_id") == scout["id"] and cand.get("target_scope_hash") == scope_hash:
            existing = (p, cand)
            break

    if existing:
        path, lug = existing
        lug["repeat_fire_count"] = int(lug.get("repeat_fire_count", 1)) + 1
        lug.setdefault("findings", []).append({
            "ts": _now_iso(),
            "session_id": session_id,
            "details": finding.get("details", {}),
            "score": finding.get("score", 0.0),
        })
        path.write_text(json.dumps(lug, indent=2))
        return str(path)

    new_id = f"bug-scout-{scout['id']}-{_utc_compact()}"
    lug = {
        "id": new_id,
        "type": "bug",
        "status": "open",
        "priority": _signal_to_priority(scout.get("signal_level", "codebase")),
        "title": f"Scout finding: {scout.get('name') or scout['id']}",
        "scout_job_id": scout["id"],
        "target_scope_hash": scope_hash,
        "verification_result": finding,
        "self_finding_subtype": finding.get("details", {}).get("self_finding_subtype"),
        "repeat_fire_count": 1,
        "findings": [{
            "ts": _now_iso(),
            "session_id": session_id,
            "details": finding.get("details", {}),
            "score": finding.get("score", 0.0),
        }],
        "run_log_ref": session_id,
        "created_at": _now_iso(),
        "created_by": "scout_executor",
    }
    out_path = BUG_LUG_DIR / f"{new_id}.json"
    out_path.write_text(json.dumps(lug, indent=2))
    return str(out_path)


def file_provider_incident_lug(provider: str, model: str, error: str, scout_id: str, session_id: str) -> str:
    BUG_LUG_DIR.mkdir(parents=True, exist_ok=True)
    bid = f"bug-provider-incident-{provider}-{_utc_compact()}"
    lug = {
        "id": bid,
        "type": "bug",
        "status": "open",
        "priority": "P2",
        "title": f"Provider incident: {provider} ({model}) — scout {scout_id}",
        "provider": provider,
        "model": model,
        "scout_job_id": scout_id,
        "error": error[:2000],
        "created_at": _now_iso(),
        "created_by": "scout_executor",
        "run_log_ref": session_id,
    }
    path = BUG_LUG_DIR / f"{bid}.json"
    path.write_text(json.dumps(lug, indent=2))
    return str(path)


# ── Orchestration ───────────────────────────────────────────────────


def _resolve_session_id() -> str:
    """Best-effort: read WAI-State.json _session_state.session_id; else stamp now."""
    state_path = _REPO_ROOT / "WAI-Spoke/WAI-State.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            sid = state.get("_session_state", {}).get("session_id")
            if sid:
                return sid
        except Exception:
            pass
    return f"adhoc-{_utc_compact()}"


def _resolve_spoke_id() -> str:
    state_path = _REPO_ROOT / "WAI-Spoke/WAI-State.json"
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
            return state.get("wheel", {}).get("wheel_id") or state.get("spoke_id", "")
        except Exception:
            pass
    return ""


def execute_one(scout: dict, model: str, provider: str, dry_run: bool, session_id: str) -> dict:
    sid = scout["id"]
    print(f"[scout] {sid}")
    payload = gather_input(scout, _REPO_ROOT)
    prompt = render_prompt(scout, payload)
    print(f"  input: {len(payload)} chars · prompt: {len(prompt)} chars")

    if dry_run:
        return {"scout_id": sid, "dry_run": True, "payload_chars": len(payload), "prompt_chars": len(prompt)}

    t0 = time.time()
    try:
        rsp = call_model(prompt, model, provider)
    except Exception as e:
        err = traceback.format_exc(limit=2)
        incident = file_provider_incident_lug(provider, model, str(e), sid, session_id)
        print(f"  ✗ provider failure; incident lug: {incident}")
        return {"scout_id": sid, "error": str(e), "incident_lug": incident}

    duration_ms = int((time.time() - t0) * 1000)
    result = run_verification(scout, rsp["text"])
    run_meta = {
        "spoke_id": _resolve_spoke_id(),
        "duration_ms": duration_ms,
        "tokens_in": rsp.get("tokens_in", 0),
        "tokens_out": rsp.get("tokens_out", 0),
    }
    emit_activity_event(scout, result, model, run_meta, session_id)

    bug_lug = None
    if not result["passed"]:
        bug_lug = file_bug_lug(scout, result, session_id, payload)

    status = "✓ PASS" if result["passed"] else "✗ FAIL"
    print(f"  {status} score={result['score']:.2f} tokens={rsp['tokens_in']}+{rsp['tokens_out']} latency={duration_ms}ms"
          + (f" bug_lug={Path(bug_lug).name}" if bug_lug else ""))

    return {
        "scout_id": sid,
        "passed": result["passed"],
        "score": result["score"],
        "duration_ms": duration_ms,
        "tokens_in": rsp["tokens_in"],
        "tokens_out": rsp["tokens_out"],
        "bug_lug": bug_lug,
        "details": result["details"],
    }


def execute_all_ready(model: str, provider: str, budget: int, dry_run: bool, session_id: str) -> dict:
    paths = list_ready_scouts()[:budget]
    print(f"[scout_executor] {len(paths)} scouts to run · provider={provider} · model={model} · dry_run={dry_run}")
    results = []
    for p in paths:
        try:
            scout = json.loads(p.read_text())
            ok, errs = _validate_scout(scout, str(SCHEMA_PATH))
            if not ok:
                print(f"[skip] {p.name}: {errs[:2]}")
                continue
            results.append(execute_one(scout, model, provider, dry_run, session_id))
        except SystemExit as e:
            print(f"[skip] {p.name}: {e}")
            continue

    if dry_run:
        summary = {"scouts_planned": len(results), "dry_run": True}
    else:
        passed = sum(1 for r in results if r.get("passed"))
        failed = sum(1 for r in results if r.get("passed") is False)
        errored = sum(1 for r in results if r.get("error"))
        bug_lugs = sum(1 for r in results if r.get("bug_lug"))
        tok_in = sum(r.get("tokens_in", 0) for r in results)
        tok_out = sum(r.get("tokens_out", 0) for r in results)
        summary = {
            "scouts_run": len(results),
            "passed": passed,
            "failed": failed,
            "errored": errored,
            "bug_lugs_filed": bug_lugs,
            "tokens_in": tok_in,
            "tokens_out": tok_out,
        }
    return {"summary": summary, "results": results}


# ── CLI ──────────────────────────────────────────────────────────────


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scout", type=str, help="Run a single scout by id or path")
    p.add_argument("--all-ready", action="store_true", help="Run all ready scouts")
    p.add_argument("--validate", type=str, help="Validate a scout file against schema and exit")
    p.add_argument("--model", type=str, default=DEFAULT_MODEL)
    p.add_argument("--provider", type=str, default=DEFAULT_PROVIDER)
    p.add_argument("--budget", type=int, default=DEFAULT_BUDGET)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--session-id", type=str, default=None)
    args = p.parse_args()

    if args.validate:
        scout, path = load_scout(args.validate)
        print(f"OK · {path}")
        return 0

    session_id = args.session_id or _resolve_session_id()

    if args.scout:
        scout, _ = load_scout(args.scout)
        result = execute_one(scout, args.model, args.provider, args.dry_run, session_id)
        print(json.dumps(result, indent=2))
        return 0

    if args.all_ready:
        out = execute_all_ready(args.model, args.provider, args.budget, args.dry_run, session_id)
        print(json.dumps(out["summary"], indent=2))
        return 0

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
