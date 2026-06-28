#!/usr/bin/env python3
"""compile_tastegraph.py — the TasteGraph producer.

Compiles user taste (``<hub>/local/taste.user.yaml``) + spoke taste
(``<base>/taste.spoke.yaml``) into the flat ``tastegraph.json`` that
``generate_wakeup_brief.py`` (and other advisors) consume at the v4 path
``<base>/tastegraph.json``. ``taste_levels.yaml`` supplies the precedence used
to resolve key collisions across levels.

Why this exists (close-the-loop gap-010): the consumers READ ``tastegraph.json``
but nothing PRODUCED it, so the file was absent and accepted user preferences
had zero path to agent behavior. This tool is the missing producer hop. It is
called at wakeup from ``generate_wakeup_brief.main()`` so the graph stays current
without a one-shot, and is also runnable standalone.

Output shape (what ``load_tastegraph_prefs`` consumes):
    {
      "schema_version": "1.0",
      "generated_at": "...",
      "generated_by": "compile_tastegraph.py",
      "parties": ["user", "<spoke_id>"],
      "source_files": {...},
      "levels": [...],            # precedence summary from taste_levels.yaml
      "counts": {...},
      "preferences": [ {id, category, key, value, confidence, source, created_at, ...}, ... ]
    }

Each preference entry conforms to wilbur/schemas/tastegraph.schema.json (the
per-entry contract); the wrapper object carries provenance metadata.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

# harness-mode root resolver (single source of truth) — sibling tool import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wai_paths  # noqa: E402

try:
    import yaml  # noqa: E402
except Exception as exc:  # pragma: no cover - environment guard
    print(f"ERROR: PyYAML is required for compile_tastegraph: {exc}", file=sys.stderr)
    raise


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _load_yaml(path: Path) -> dict:
    """Parse a YAML file to a dict; missing/empty/broken -> {} (never raises)."""
    if not path or not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _confidence_from_status(status: str) -> str:
    """Map a taste entry status to a TasteGraph confidence band.

    accepted -> verified  (user explicitly confirmed; injected by consumers)
    proposed/pending/draft -> inferred (unconfirmed; filtered OUT of injection)
    anything else (already stated/verified) -> passed through.
    """
    s = (status or "").strip().lower()
    if s == "accepted":
        return "verified"
    if s in ("stated", "verified", "inferred"):
        return s
    return "inferred"


def _entry_to_pref(entry: dict, level: str, value_field: str) -> dict | None:
    """Convert one taste.*.yaml entry into a schema-shaped preference dict.

    value_field is "preference" (user yaml) or "statement" (spoke yaml).
    Returns None for entries with no usable value text.
    """
    eid = str(entry.get("id") or "").strip()
    value = entry.get(value_field) or entry.get("preference") or entry.get("statement")
    if not eid or not value:
        return None
    created = (
        entry.get("proposed_at")
        or entry.get("accepted_at")
        or entry.get("created_at")
        or _now()
    )
    src = entry.get("source") or entry.get("session_source") or entry.get("proposed_by") or "taste"
    return {
        "id": eid,
        "category": entry.get("category") or "other",
        "key": eid,
        "value": value,
        "confidence": _confidence_from_status(entry.get("status", "")),
        "source": f"{src} [level:{level}]",
        "created_at": created,
        "last_verified": entry.get("accepted_at"),
        "notes": None,
    }


def _level_weight(levels_cfg: dict, level_name: str) -> int:
    """Precedence weight for a level name from taste_levels.yaml (higher wins).

    user preferences map to the 'individual' hierarchy level; spoke to 'spoke'.
    Defaults keep user (50) above spoke (40) when the config is absent.
    """
    alias = {"user": "individual", "spoke": "spoke"}.get(level_name, level_name)
    for lvl in levels_cfg.get("hierarchy_levels", []) or []:
        if lvl.get("name") == alias:
            try:
                return int(lvl.get("weight", 0))
            except Exception:
                return 0
    return {"individual": 50, "spoke": 40}.get(alias, 0)


def resolve_hub_path(project_root: Path, mode: str | None, hub_path: str | None) -> Path | None:
    """Resolve the hub directory that holds local/taste.user.yaml.

    Order: explicit arg -> WAI-State.json wheel.hub_path -> <root>/WAI-Harness/hub.
    """
    if hub_path:
        p = Path(hub_path)
        if p.exists():
            return p
    base, _ = wai_paths.resolve_wai_root(str(project_root), mode)
    if base:
        state_file = Path(base) / "WAI-State.json"
        if state_file.exists():
            try:
                hp = json.loads(state_file.read_text()).get("wheel", {}).get("hub_path", "")
                if hp and Path(hp).exists():
                    return Path(hp)
            except Exception:
                pass
    fallback = project_root / "WAI-Harness" / "hub"
    return fallback if fallback.exists() else None


def compile_tastegraph(
    project_root: str | Path = ".",
    mode: str | None = None,
    hub_path: str | None = None,
    write: bool = True,
) -> dict:
    """Compile the TasteGraph and (optionally) write it to <base>/tastegraph.json.

    Returns {"ok", "path", "graph", "counts", "error"}.
    """
    project_root = Path(project_root)
    base_str, active = wai_paths.resolve_wai_root(str(project_root), mode)
    if not base_str:
        return {"ok": False, "error": "no WAI harness tree (WAI-Spoke/WAI-Harness)", "path": None, "graph": None}
    base = Path(base_str)

    spoke_id = "spoke"
    state_file = base / "WAI-State.json"
    if state_file.exists():
        try:
            spoke_id = json.loads(state_file.read_text()).get("wheel", {}).get("name", "spoke")
        except Exception:
            pass

    hub = resolve_hub_path(project_root, mode, hub_path)
    user_yaml = (hub / "local" / "taste.user.yaml") if hub else None
    spoke_yaml = base / "taste.spoke.yaml"
    # taste_levels.yaml is a managed config that ships beside this tool's tree.
    levels_yaml = Path(__file__).resolve().parent.parent / "config" / "taste_levels.yaml"

    user_doc = _load_yaml(user_yaml) if user_yaml else {}
    spoke_doc = _load_yaml(spoke_yaml)
    levels_cfg = _load_yaml(levels_yaml)

    # Build preferences keyed by `key`; on collision the higher-precedence level wins.
    by_key: dict[str, tuple[int, dict]] = {}

    def _ingest(entries, level, value_field):
        weight = _level_weight(levels_cfg, level)
        for entry in entries or []:
            pref = _entry_to_pref(entry, level, value_field)
            if not pref:
                continue
            k = pref["key"]
            if k not in by_key or weight > by_key[k][0]:
                by_key[k] = (weight, pref)

    _ingest(user_doc.get("entries", []), "user", "preference")
    _ingest(spoke_doc.get("entries", []), "spoke", "statement")

    preferences = [p for _, p in by_key.values()]
    # Stable order: category, then id — deterministic output across runs.
    preferences.sort(key=lambda p: (p.get("category", ""), p.get("id", "")))

    confidences: dict[str, int] = {}
    for p in preferences:
        confidences[p["confidence"]] = confidences.get(p["confidence"], 0) + 1

    graph = {
        "schema_version": "1.0",
        "generated_at": _now(),
        "generated_by": "compile_tastegraph.py",
        "harness_mode": active,
        "parties": ["user", spoke_id],
        "source_files": {
            "user": str(user_yaml) if user_yaml and user_yaml.exists() else None,
            "spoke": str(spoke_yaml) if spoke_yaml.exists() else None,
            "levels": str(levels_yaml) if levels_yaml.exists() else None,
        },
        "levels": [
            {"name": lvl.get("name"), "weight": lvl.get("weight")}
            for lvl in (levels_cfg.get("hierarchy_levels", []) or [])
        ],
        "counts": {
            "total": len(preferences),
            "by_confidence": confidences,
            "user_entries": len(user_doc.get("entries", []) or []),
            "spoke_entries": len(spoke_doc.get("entries", []) or []),
        },
        "preferences": preferences,
    }

    out_path = base / "tastegraph.json"
    if write:
        out_path.write_text(json.dumps(graph, indent=2) + "\n")

    return {
        "ok": True,
        "path": str(out_path),
        "graph": graph,
        "counts": graph["counts"],
        "error": None,
    }


def _main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compile the TasteGraph (user + spoke taste -> tastegraph.json).")
    parser.add_argument("--spoke-path", default=".", help="Spoke project root (contains WAI-Harness/WAI-Spoke).")
    parser.add_argument("--mode", default=None, help="v4-only | v3-only (else $WAI_HARNESS_MODE / auto).")
    parser.add_argument("--hub-path", default=None, help="Override hub directory holding local/taste.user.yaml.")
    parser.add_argument("--dry-run", action="store_true", help="Compile and print summary without writing the file.")
    parser.add_argument("--json", action="store_true", help="Print the full compiled graph as JSON.")
    args = parser.parse_args(argv)

    result = compile_tastegraph(
        project_root=args.spoke_path,
        mode=args.mode,
        hub_path=args.hub_path,
        write=not args.dry_run,
    )
    if not result["ok"]:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result["graph"], indent=2))
    else:
        c = result["counts"]
        action = "(dry-run, not written)" if args.dry_run else f"-> {result['path']}"
        print(
            f"TasteGraph compiled {action}: {c['total']} prefs "
            f"({c['user_entries']} user + {c['spoke_entries']} spoke) "
            f"confidence={c['by_confidence']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
