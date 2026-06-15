#!/usr/bin/env python3
"""CapabilitiesGraph resolver (spec-capabilitiesgraph-v1).

The CG is the POLICY circle: what a wheel is EXPECTED to be able to do and how
strongly that is required (tier), inherited hub -> group -> spoke -> local.

This resolves the inheritance chain into the authoritative effective bar
(capabilities-effective.json), enforcing the two axes:

  - BEHAVIOR axis (tier, situation, solution, verification_ref): mandated wins.
    A later layer cannot weaken a hub-mandated entry — the override is BLOCKED
    and recorded as a decision (design ss15: schema hard-block on local overrides
    of mandated CG namespaces; AC45: a spoke cannot weaken a mandated guardrail).
  - CONFIG axis (run, owner_advisor, command, valid_until, file_paths): local wins.

Superset rule: a non-hub layer may NOT author a NEW tier=mandated entry (mandated
is a fleet decision canonicalized by the hub Trainer). Such an entry is downgraded
to recommended + a decision instructs bubble-up.

Every resolved entry carries an inheritance_trace [{layer, axis, action, from_source}]
so the resolved layer is observable.

Pure core: resolve_capabilities_graph(layers) -> {entries, decisions}. The CLI
wraps it with file IO over the MyWheel master tree.
"""
import argparse
import json
import os
import sys

LAYER_ORDER = ["hub", "group", "spoke", "local"]
BEHAVIOR_FIELDS = ("tier", "situation", "solution", "verification_ref")
CONFIG_FIELDS = ("run", "owner_advisor", "command", "valid_until", "file_paths", "symbol_refs")
_VALID_TIERS = {"mandated", "recommended", "awareness"}


def _is_hub_mandated(entry):
    return entry.get("source") == "hub" and entry.get("tier") == "mandated"


def resolve_capabilities_graph(layers):
    """Resolve an ordered list of layers into the effective CG.

    layers: ordered list of {"source": "hub"|"group"|"spoke"|"local",
                             "entries": [ capability_entry, ... ]}
            (caller supplies them in hub->group->spoke->local order)

    Returns {"entries": [resolved...], "decisions": [decision events...]}.
    Pure — no file IO, deterministic.
    """
    resolved = {}      # id -> entry (with inheritance_trace)
    decisions = []

    for layer in layers:
        src = layer.get("source")
        for raw in layer.get("entries", []):
            cid = raw.get("id")
            if not cid:
                continue
            entry = dict(raw)
            entry["source"] = src

            if cid not in resolved:
                # First introduction. Superset rule: only hub may introduce mandated.
                if entry.get("tier") == "mandated" and src != "hub":
                    decisions.append({
                        "type": "decision",
                        "kind": "mandated-downgrade",
                        "capability": cid,
                        "from_source": src,
                        "rationale": "a non-hub layer cannot author a NEW mandated capability "
                                     "(mandated is a fleet decision); downgraded to recommended. "
                                     "Bubble it up to the hub as a change-lug to make it mandated.",
                    })
                    entry["tier"] = "recommended"
                    entry["inheritance_trace"] = [
                        {"layer": src, "axis": "behavior", "action": "downgraded", "from_source": src}
                    ]
                else:
                    entry["inheritance_trace"] = [
                        {"layer": src, "axis": "behavior", "action": "introduced", "from_source": src}
                    ]
                resolved[cid] = entry
                continue

            # --- override of an existing entry ---
            base = resolved[cid]
            base_is_mandated = _is_hub_mandated(base)
            trace = base.get("inheritance_trace", [])

            for field, val in entry.items():
                if field in ("id", "inheritance_trace", "source"):
                    continue
                if field in BEHAVIOR_FIELDS:
                    if base_is_mandated and base.get(field) != val:
                        # BLOCK: cannot weaken/alter a hub-mandated behavior field
                        decisions.append({
                            "type": "decision",
                            "kind": "mandated-override-blocked",
                            "capability": cid,
                            "field": field,
                            "from_source": src,
                            "attempted": val,
                            "kept": base.get(field),
                            "rationale": "behavior-axis override of a hub-mandated capability is "
                                         "blocked (a spoke cannot weaken a mandated guardrail).",
                        })
                        trace.append({"layer": src, "axis": "behavior",
                                      "action": "blocked", "from_source": src, "field": field})
                        # base value retained (no mutation)
                    elif not base_is_mandated and base.get(field) != val:
                        base[field] = val
                        trace.append({"layer": src, "axis": "behavior",
                                      "action": "overridden", "from_source": src, "field": field})
                elif field in CONFIG_FIELDS:
                    # config axis: local (later layer) wins
                    if base.get(field) != val:
                        base[field] = val
                        trace.append({"layer": src, "axis": "config",
                                      "action": "overridden", "from_source": src, "field": field})
                else:
                    # non-classified field (status, decision_rationale, etc.): later layer sets it
                    base[field] = val
            base["inheritance_trace"] = trace

    return {"entries": list(resolved.values()), "decisions": decisions}


# --------------------------------------------------------------------------- #
# File IO / CLI over the MyWheel master tree
# --------------------------------------------------------------------------- #

def _read_layer(path, source):
    if not path or not os.path.exists(path):
        return {"source": source, "entries": []}
    data = json.load(open(path))
    # accept either {"components"/"entries":[...]} or a bare list
    if isinstance(data, list):
        entries = data
    else:
        entries = data.get("entries") or data.get("capabilities") or data.get("components") or []
    return {"source": source, "entries": entries}


def resolve_from_tree(mywheel_path):
    hub = os.path.join(mywheel_path, "WAI-Harness/hub/managed/capabilities-graph-hub.json")
    spoke = os.path.join(mywheel_path, "WAI-Harness/spoke/managed/capabilities-graph.json")
    local = os.path.join(mywheel_path, "WAI-Harness/spoke/local/capabilities-graph-local.json")
    layers = [
        _read_layer(hub, "hub"),
        _read_layer(spoke, "spoke"),
        _read_layer(local, "local"),
    ]
    return resolve_capabilities_graph(layers)


def main(argv):
    ap = argparse.ArgumentParser(description="Resolve the CapabilitiesGraph inheritance chain.")
    ap.add_argument("--mywheel-path", default="/home/mario/projects/wheelwright/mywheel")
    ap.add_argument("--out", default=None,
                    help="output path (default: <mywheel>/WAI-Harness/spoke/managed/runtime/capabilities-effective.json)")
    args = ap.parse_args(argv)

    result = resolve_from_tree(args.mywheel_path)
    out = args.out or os.path.join(
        args.mywheel_path, "WAI-Harness/spoke/managed/runtime/capabilities-effective.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump({"entries": result["entries"], "decisions": result["decisions"],
               "resolved_count": len(result["entries"])}, open(out, "w"), indent=2)
    print(f"resolved {len(result['entries'])} capabilities -> {out}")
    if result["decisions"]:
        print(f"  {len(result['decisions'])} decision event(s):")
        for d in result["decisions"]:
            print(f"    - {d['kind']}: {d['capability']} ({d.get('field','')})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
