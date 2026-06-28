#!/usr/bin/env python3
"""change_registry.py — the empower-but-control plane for harness/cross-spoke change.

(impl-change-registry-core-v1, spec-harness-development-control-v1) Any node may
ORIGINATE a change to another spoke or to the harness master — but every remote
change is mediated by this registry so it is verifiable, attributable, and
maintained by the receiving (native) agent rather than silently mutated.

The balance:
  empower  — any spoke/hub may propose a change (curator model).
  control  — a remote change without a registry entry is a protocol violation
             (silent mutation) — flagged and reverted.
  native   — only the TARGET spoke's agent advances incorporation_status; the
             originator proposes + registers, the native agent accepts/maintains.
  master   — a change targeting MyWheel is not distributable until Trainer
             canonicalizes it.

Reuses tools/write_change_receipt.py for the actual delivery; this module is the
ledger + the guards. Pure functions over an injected registry path so the
control plane is itself unit-tested.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REQUIRED_KEYS = ("change_id", "origin", "target", "scope", "what_changed", "why", "files")
VALID_SCOPES = ("spoke-file", "harness-managed", "harness-hub", "new-spoke")
# only the native (target) agent may advance to these:
NATIVE_ONLY_STATUSES = ("accepted", "adapted", "rejected", "maintained")


def _registry_base(spoke_root="."):
    """The spoke working base holding runtime/, base-aware. On a v4 spoke this
    resolves to WAI-Harness/spoke/local; PRE-FIX the hardcoded WAI-Spoke default
    wrote the ledger into a nonexistent tree (impl-fix-p2-v3noop-sweep-v1)."""
    try:
        from wai_paths import resolve_wai_root
        root, mode = resolve_wai_root(str(spoke_root))
        if root and mode != "none":
            return Path(root)
    except Exception:
        pass
    return Path(spoke_root) / "WAI-Spoke"  # last-resort v3 fallback


DEFAULT_REGISTRY = str(_registry_base() / "runtime" / "change-registry.jsonl")


class RegistryError(ValueError):
    """A registry operation violated the control-plane rules."""


def _read(registry_path):
    if not os.path.exists(registry_path):
        return []
    out = []
    with open(registry_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _append(entry, registry_path):
    os.makedirs(os.path.dirname(os.path.abspath(registry_path)), exist_ok=True)
    with open(registry_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")


def register_change(entry, registry_path=DEFAULT_REGISTRY, now_iso=None):
    """Record a remote/harness change. Sets the default control fields and
    appends to the per-spoke registry ledger. Rejects an incomplete entry."""
    missing = [k for k in REQUIRED_KEYS if not entry.get(k)]
    if missing:
        raise RegistryError(f"registry entry missing required key(s): {missing}")
    if entry.get("scope") not in VALID_SCOPES:
        raise RegistryError(f"invalid scope {entry.get('scope')!r}; must be one of {VALID_SCOPES}")
    e = dict(entry)
    e.setdefault("incorporation_status", "registered")
    e.setdefault("incorporated_by", None)
    # maintenance is ALWAYS the target spoke once incorporated — never the originator
    e["maintenance_owner"] = e.get("target")
    e["registered_at"] = now_iso
    e.setdefault("commit", None)
    if e["target"] == "MyWheel":
        e.setdefault("canonicalized_by_trainer", None)
    _append(e, registry_path)
    return e


def advance_status(change_id, new_status, by_spoke, registry_path=DEFAULT_REGISTRY):
    """Advance a change's incorporation_status. ONLY the target spoke's native
    agent may move it to accepted/adapted/rejected/maintained — the originator
    cannot self-mark its own proposal accepted."""
    entries = _read(registry_path)
    match = None
    for e in entries:
        if e.get("change_id") == change_id:
            match = e
    if not match:
        raise RegistryError(f"no registry entry for change_id {change_id!r}")
    if new_status in NATIVE_ONLY_STATUSES and by_spoke != match.get("target"):
        raise RegistryError(
            f"only the native target spoke ({match.get('target')!r}) may advance "
            f"status to {new_status!r}; {by_spoke!r} is the originator/other")
    match["incorporation_status"] = new_status
    match["incorporated_by"] = by_spoke
    # rewrite the ledger (small, append-only file)
    with open(registry_path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, separators=(",", ":")) + "\n")
    return match


def silent_mutation_guard(remote_writes, registry_entries):
    """A remote write to another spoke MUST be covered by a registry entry. Any
    write with no covering entry is a silent mutation — flagged for revert.
    remote_writes: [{target, files:[...]}]. A write is covered when an entry has
    the same target and at least one overlapping file."""
    covered = []
    for e in registry_entries:
        covered.append((e.get("target"), set(e.get("files", []))))
    flagged = []
    for w in remote_writes:
        t, files = w.get("target"), set(w.get("files", []))
        ok = any(t == ct and (files & cf) for ct, cf in covered)
        if not ok:
            flagged.append(w)
    return {"flagged": flagged, "action": "revert" if flagged else "none",
            "ok": not flagged}


def check_rev(current_rev, write_against_rev):
    """Optimistic concurrency for lug writes: a write prepared against a stale rev
    is rejected and surfaced for reconcile. Last-write-wins is BANNED — divergence
    must be surfaced, not silently resolved."""
    if write_against_rev is None or current_rev is None:
        return {"ok": False, "reason": "missing rev — cannot apply (last-write-wins banned)"}
    if write_against_rev < current_rev:
        return {"ok": False, "stale": True,
                "reason": f"write prepared against rev {write_against_rev} but current is "
                          f"{current_rev} — reconcile required, not silent overwrite"}
    return {"ok": True, "next_rev": current_rev + 1}


def requires_trainer_canonicalization(entry):
    """A harness-master change (target=MyWheel) needs Trainer canonicalization."""
    return entry.get("target") == "MyWheel"


def is_distributable(entry):
    """Can Basher distribute this change? A MyWheel-master change is held until
    Trainer canonicalizes it; everything else is distributable once registered."""
    if requires_trainer_canonicalization(entry):
        return bool(entry.get("canonicalized_by_trainer"))
    return True


def new_spoke_entry(origin, new_wheel_id, blueprint_version, path=None, now_iso=None):
    """Produce the scope='new-spoke' registry entry + the hub-registration record.
    A new spoke is not 'live' until registered in the hub registry + reporting a
    certification score."""
    entry = {"change_id": f"new-spoke-{new_wheel_id}", "origin": origin,
             "target": new_wheel_id, "scope": "new-spoke",
             "what_changed": f"bootstrapped new spoke {new_wheel_id} from MyWheel blueprint",
             "why": "spoke creation from any node (removes central bottleneck)",
             "files": ["WAI-Harness/spoke/ (own-copy)"], "registered_at": now_iso}
    registration = {"wheel_id": new_wheel_id, "path": path,
                    "blueprint_version": blueprint_version,
                    "advisors": [], "initiatives": [],
                    "certification_score": None, "status": "registered-degraded"}
    return {"registry_entry": entry, "hub_registration": registration}


if __name__ == "__main__":
    print("change_registry: register_change, advance_status, silent_mutation_guard, "
          "check_rev, is_distributable, new_spoke_entry")
