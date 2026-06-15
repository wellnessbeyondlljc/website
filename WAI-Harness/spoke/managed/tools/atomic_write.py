#!/usr/bin/env python3
"""atomic_write.py — stage → validate → commit-on-pass file mutations (no partial writes).

Part of the execution sandbox (impl-execution-sandbox-foundation-v1). An agent-
authored mutation is never applied directly to a live file. The content is
staged to a sibling .staging path, validated (py_compile for .py, json.load for
.json, optional named schema), and only os.replace()'d onto the live target on
pass — which is atomic on POSIX. On failure the staging copy is discarded, a
failure event is emitted, and the live target is left byte-for-byte unchanged.

API:
  atomic_write(target_path, content, schema_path=None, journal_path=None)
      -> {"committed": bool, "reason": str, "target": path}
"""
import argparse
import json
import os
import py_compile
import sys
import tempfile

try:
    import event_bus
except ImportError:  # event bus is optional at this layer; failures still surface via return
    event_bus = None


def _validate(staging_path, target_path, schema_path):
    ext = os.path.splitext(target_path)[1].lower()
    if ext == ".py":
        try:
            py_compile.compile(staging_path, doraise=True)
        except py_compile.PyCompileError as e:
            return False, f"py_compile failed: {e.msg.strip()}"
    elif ext in (".json",):
        try:
            with open(staging_path, encoding="utf-8") as f:
                data = json.load(f)
        except ValueError as e:
            return False, f"json parse failed: {e}"
        if schema_path:
            ok, why = _schema_check(data, schema_path)
            if not ok:
                return False, why
    return True, "valid"


def _schema_check(data, schema_path):
    """Minimal required-keys schema check (no jsonschema dependency)."""
    try:
        schema = json.load(open(schema_path, encoding="utf-8"))
    except (ValueError, OSError) as e:
        return False, f"schema unreadable: {e}"
    required = schema.get("required", [])
    missing = [k for k in required if k not in (data or {})]
    if missing:
        return False, f"schema: missing required keys {missing}"
    return True, "schema ok"


def _emit_failure(target_path, reason, journal_path):
    if event_bus is None:
        return
    try:
        ev = {"ts": _now(), "type": "atomic_write_failure", "actor": "sandbox",
              "status": "discarded", "subject_ref": target_path,
              "evidence": {"reason": reason}}
        kw = {"journal_path": journal_path} if journal_path else {}
        event_bus.emit(ev, **kw)
    except Exception:
        pass


def _now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def atomic_write(target_path, content, schema_path=None, journal_path=None):
    """Stage, validate, and atomically commit `content` to `target_path`.
    Returns a result dict; never leaves a partial write."""
    target_path = os.path.abspath(target_path)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    # stage in the same directory so os.replace is a same-filesystem atomic rename
    fd, staging = tempfile.mkstemp(dir=os.path.dirname(target_path),
                                   prefix=".staging-", suffix=os.path.splitext(target_path)[1])
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        ok, reason = _validate(staging, target_path, schema_path)
        if not ok:
            os.remove(staging)
            _emit_failure(target_path, reason, journal_path)
            return {"committed": False, "reason": reason, "target": target_path}
        os.replace(staging, target_path)  # atomic
        return {"committed": True, "reason": "committed", "target": target_path}
    except Exception as e:
        if os.path.exists(staging):
            os.remove(staging)
        _emit_failure(target_path, f"exception: {e}", journal_path)
        return {"committed": False, "reason": f"exception: {e}", "target": target_path}


def main(argv=None):
    ap = argparse.ArgumentParser(description="atomic stage→validate→commit write")
    ap.add_argument("target")
    ap.add_argument("--content-file", required=True, help="file whose bytes become the new content")
    ap.add_argument("--schema")
    ap.add_argument("--journal-path")
    a = ap.parse_args(argv)
    content = open(a.content_file, encoding="utf-8").read()
    res = atomic_write(a.target, content, a.schema, a.journal_path)
    print(json.dumps(res))
    return 0 if res["committed"] else 1


if __name__ == "__main__":
    sys.exit(main())
