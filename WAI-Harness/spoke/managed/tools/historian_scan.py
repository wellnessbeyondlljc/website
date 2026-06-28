#!/usr/bin/env python3
"""
Historian pattern scan — reads all session tracks, clusters patterns,
updates vectors.jsonl, scan_state.json, and passes.jsonl.

READ-ONLY on track files. Writes only to WAI-Spoke/advisors/historian/.
"""

import json
import os
import re
import string
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

# ── Config ──────────────────────────────────────────────────────────
# v4-aware (gap-003): resolve the running spoke's working base instead of a hardcoded
# framework/WAI-Spoke path (which no longer exists post-migration). Spoke root comes
# from $WAI_SPOKE_ROOT or cwd; wai_paths resolves v3-vs-v4 with a v4 default on
# activated spokes. LEGACY_DIRS are the relocated legacy track stores the historian
# must ALSO mine (internal archive + in-place residual) so forgotten history isn't lost.
import sys as _sys
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in _sys.path:
    _sys.path.insert(0, str(_HERE))
try:
    import wai_paths as _wp
    _ROOT = Path(os.environ.get("WAI_SPOKE_ROOT", ".")).resolve()
    _b = _wp.resolve_wai_root(str(_ROOT))[0]
    if _b:
        BASE = Path(_b)
    elif (_ROOT / "WAI-Harness" / "spoke" / "local").is_dir():
        BASE = _ROOT / "WAI-Harness" / "spoke" / "local"
    else:
        BASE = _ROOT / "WAI-Spoke"
    _adv = _wp.advisors_dir(str(_ROOT))
    HISTORIAN_DIR = Path(_adv) / "historian" if _adv else BASE / "advisors" / "historian"
except Exception:
    # last-resort: operate relative to cwd's v4 tree
    BASE = Path(os.environ.get("WAI_SPOKE_ROOT", ".")).resolve() / "WAI-Harness" / "spoke" / "local"
    HISTORIAN_DIR = BASE / "advisors" / "historian"

SESSIONS_DIR = BASE / "sessions"
# Relocated/legacy track stores to ALSO mine (internal archive + in-place residual).
LEGACY_DIRS = [
    BASE.parent / "archive" / "v3-snapshot" / "sessions",   # WAI-Harness/spoke/archive/v3-snapshot
    BASE.parent.parent.parent / "WAI-Spoke" / "sessions",   # in-place residual WAI-Spoke
]
VECTORS_FILE = HISTORIAN_DIR / "vectors.jsonl"
SCAN_STATE_FILE = HISTORIAN_DIR / "scan_state.json"
PASSES_FILE = HISTORIAN_DIR / "passes.jsonl"

JACCARD_THRESHOLD = 0.3
OPEN_RECURRENCE_MIN_SESSIONS = 3
WORKAROUND_CHURN_MIN_OCCURRENCES = 4
WORKAROUND_CHURN_MIN_SESSIONS = 2
REOPENED_DECISION_MIN_SESSIONS = 2

ACTIVITY_SKIP_VERBS = {
    "added", "adopted", "appended", "applied", "bumped", "checked",
    "closed", "committed", "confirmed", "converted", "copied", "created",
    "deleted", "detected", "fixed", "initialized", "installed", "loaded",
    "merged", "moved", "parsed", "pushed", "ran", "read", "reconciled",
    "removed", "replaced", "staged", "updated", "verified"
}

STOP_WORDS = {
    "a", "an", "the", "is", "was", "were", "has", "have", "had", "be",
    "been", "to", "of", "in", "on", "at", "for", "with", "from", "as",
    "this", "that", "not", "but"
}


def tokenize(text):
    """Lowercase, strip punctuation, remove stop words."""
    text = text.lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    tokens = text.split()
    return set(t for t in tokens if t not in STOP_WORDS)


def jaccard(tokens_a, tokens_b):
    """Jaccard similarity between two token sets."""
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


# ── Step 1: Load all session tracks ────────────────────────────────
print("=== Historian Pattern Scan ===\n")

session_dirs = sorted(SESSIONS_DIR.glob("session-*/"))
# Also mine relocated/legacy track stores so migrated-away history isn't lost.
for _legacy in LEGACY_DIRS:
    if _legacy.is_dir():
        session_dirs += sorted(_legacy.glob("session-*/"))
items = []  # list of (text, session_id, turn, field, tokens)

total_points = 0
session_ids_processed = []

for session_dir in session_dirs:
    track_file = session_dir / "track.jsonl"
    if not track_file.exists():
        continue

    session_id = session_dir.name
    session_ids_processed.append(session_id)

    with open(track_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                point = json.loads(line)
            except json.JSONDecodeError:
                continue

            total_points += 1
            turn = point.get("turn", 0)

            # Extract open[] items
            for item in point.get("open", []):
                if isinstance(item, dict):
                    # JSON object with {text, type}
                    item_text = item.get("text", "")
                    item_type = item.get("type", "")
                    if item_type in ("intentional", "deferred"):
                        # Will be filtered in Step 2 unless 6+ sessions
                        # Mark for deferred filtering
                        items.append((item_text, session_id, turn, "open_deferred", tokenize(item_text)))
                    else:
                        items.append((item_text, session_id, turn, "open", tokenize(item_text)))
                elif isinstance(item, str):
                    items.append((item, session_id, turn, "open", tokenize(item)))

            # Extract activity[] items
            for item in point.get("activity", []):
                if isinstance(item, str):
                    items.append((item, session_id, turn, "activity", tokenize(item)))

            # Extract decisions[] items
            for item in point.get("decisions", []):
                if isinstance(item, str):
                    items.append((item, session_id, turn, "decisions", tokenize(item)))

print(f"Sessions found: {len(session_ids_processed)}")
print(f"Total track points: {total_points}")
print(f"Raw items extracted: {len(items)}")

# ── Step 2: Filter ─────────────────────────────────────────────────
# Filter activity items by first verb
filtered_items = []
activity_filtered = 0
deferred_open_items = []  # collect deferred/intentional open items for 6+ session check

for text, session_id, turn, field, tokens in items:
    if field == "activity":
        first_word = text.strip().lower().split()[0] if text.strip() else ""
        if first_word in ACTIVITY_SKIP_VERBS:
            activity_filtered += 1
            continue
        filtered_items.append((text, session_id, turn, field, tokens))
    elif field == "open_deferred":
        deferred_open_items.append((text, session_id, turn, tokens))
    else:
        filtered_items.append((text, session_id, turn, field, tokens))

# Check deferred open items: keep only if they appear in 6+ distinct sessions
deferred_by_text = defaultdict(set)
for text, session_id, turn, tokens in deferred_open_items:
    deferred_by_text[text].add(session_id)

deferred_kept = 0
deferred_dropped = 0
for text, session_id, turn, tokens in deferred_open_items:
    if len(deferred_by_text[text]) >= 6:
        filtered_items.append((text, session_id, turn, "open", tokens))
        deferred_kept += 1
    else:
        deferred_dropped += 1

print(f"Activity items filtered (routine verbs): {activity_filtered}")
print(f"Deferred/intentional open items kept (6+ sessions): {deferred_kept}")
print(f"Deferred/intentional open items dropped: {deferred_dropped}")
print(f"Items after filtering: {len(filtered_items)}")

# ── Step 3: Token-normalize and cluster ─────────────────────────────
# Group by field type for clustering
by_field = defaultdict(list)
for text, session_id, turn, field, tokens in filtered_items:
    by_field[field].append((text, session_id, turn, tokens))

# Cluster using single-linkage with Jaccard >= 0.3
def cluster_items(item_list):
    """Cluster items by Jaccard similarity >= threshold using union-find."""
    n = len(item_list)
    if n == 0:
        return []

    # Union-Find
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # Compare items from DIFFERENT sessions only
    for i in range(n):
        for j in range(i + 1, n):
            # Only cluster across different sessions
            if item_list[i][1] == item_list[j][1]:
                continue
            sim = jaccard(item_list[i][3], item_list[j][3])
            if sim >= JACCARD_THRESHOLD:
                union(i, j)

    # Group by cluster
    clusters = defaultdict(list)
    for i in range(n):
        clusters[find(i)].append(i)

    return [indices for indices in clusters.values() if len(indices) > 1]

all_clusters = []

for field, field_items in by_field.items():
    clusters = cluster_items(field_items)
    for indices in clusters:
        cluster_data = {
            "field": field,
            "items": [(field_items[i][0], field_items[i][1], field_items[i][2]) for i in indices],
            "tokens": [field_items[i][3] for i in indices],
            "sessions": set(field_items[i][1] for i in indices),
            "total_occurrences": len(indices),
        }
        # Pick the most representative text (longest)
        cluster_data["sample_text"] = max(
            [field_items[i][0] for i in indices], key=len
        )
        all_clusters.append(cluster_data)

print(f"\nClusters found (across fields): {len(all_clusters)}")

# ── Step 4: Classify patterns ──────────────────────────────────────
patterns = []

for cluster in all_clusters:
    field = cluster["field"]
    n_sessions = len(cluster["sessions"])
    n_occurrences = cluster["total_occurrences"]

    pattern_type = None
    meets_threshold = False

    if field == "open":
        if n_sessions >= OPEN_RECURRENCE_MIN_SESSIONS:
            pattern_type = "open_recurrence"
            meets_threshold = True
    elif field == "activity":
        if n_occurrences >= WORKAROUND_CHURN_MIN_OCCURRENCES or n_sessions >= WORKAROUND_CHURN_MIN_SESSIONS:
            pattern_type = "workaround_churn"
            meets_threshold = True
    elif field == "decisions":
        if n_sessions >= REOPENED_DECISION_MIN_SESSIONS:
            pattern_type = "reopened_decision"
            meets_threshold = True

    if meets_threshold:
        # Compute similarity scores within cluster
        sim_scores = []
        items_list = cluster["items"]
        tokens_list = cluster["tokens"]
        for i in range(len(items_list)):
            for j in range(i + 1, len(items_list)):
                if items_list[i][1] != items_list[j][1]:  # different sessions
                    sim = jaccard(tokens_list[i], tokens_list[j])
                    if sim >= JACCARD_THRESHOLD:
                        sim_scores.append(round(sim, 2))

        evidence = []
        for text, sid, turn in cluster["items"]:
            evidence.append(f"{sid} turn {turn} {field}[]")

        sorted_sessions = sorted(cluster["sessions"])

        patterns.append({
            "pattern_type": pattern_type,
            "sample_text": cluster["sample_text"],
            "description": f"{cluster['sample_text'][:80]} — {n_sessions} sessions, {n_occurrences} occurrences",
            "sessions": sorted_sessions,
            "n_sessions": n_sessions,
            "n_occurrences": n_occurrences,
            "first_seen": sorted_sessions[0],
            "last_seen": sorted_sessions[-1],
            "similarity_scores": sorted(sim_scores, reverse=True)[:10],
            "evidence": evidence[:15],
            "field": field,
        })

print(f"Patterns meeting thresholds: {len(patterns)}")

# ── Step 5: Update vectors ──────────────────────────────────────────
existing_vectors = []
if VECTORS_FILE.exists():
    with open(VECTORS_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    existing_vectors.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

print(f"\nExisting vectors: {len(existing_vectors)}")

# Track updates
vectors_updated = 0
vectors_created = 0
updated_vector_ids = []
new_vector_entries = []

now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
scan_ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")

for pattern in patterns:
    pattern_tokens = tokenize(pattern["sample_text"])

    # Check against existing vectors
    best_match = None
    best_sim = 0
    for i, vec in enumerate(existing_vectors):
        vec_tokens = tokenize(vec.get("sample_text", ""))
        sim = jaccard(pattern_tokens, vec_tokens)
        if sim >= JACCARD_THRESHOLD and sim > best_sim:
            best_match = i
            best_sim = sim

    if best_match is not None:
        # Update existing vector
        vec = existing_vectors[best_match]
        vec["last_seen"] = pattern["last_seen"]
        vec["occurrences"] = max(vec.get("occurrences", 0), pattern["n_occurrences"])
        # Append new similarity scores
        existing_scores = vec.get("similarity_scores", [])
        for s in pattern["similarity_scores"]:
            if s not in existing_scores:
                existing_scores.append(s)
        vec["similarity_scores"] = sorted(existing_scores, reverse=True)[:15]
        # Extend evidence
        existing_evidence = set(vec.get("evidence", []))
        for e in pattern["evidence"]:
            existing_evidence.add(e)
        vec["evidence"] = sorted(existing_evidence)[:20]

        vectors_updated += 1
        updated_vector_ids.append(vec["id"])
    else:
        # Create new vector
        vector_num = len(existing_vectors) + len(new_vector_entries) + 1
        new_vec = {
            "id": f"vector-{scan_ts}-{vector_num:02d}",
            "created": now_iso,
            "pattern_type": pattern["pattern_type"],
            "description": pattern["description"],
            "sample_text": pattern["sample_text"],
            "first_seen": pattern["first_seen"],
            "last_seen": pattern["last_seen"],
            "occurrences": pattern["n_occurrences"],
            "similarity_scores": pattern["similarity_scores"],
            "status": "watching",
            "threshold": {
                "open_recurrence": OPEN_RECURRENCE_MIN_SESSIONS,
                "workaround_churn": WORKAROUND_CHURN_MIN_OCCURRENCES,
                "reopened_decision": REOPENED_DECISION_MIN_SESSIONS,
            }.get(pattern["pattern_type"], 3),
            "investigation_prompt": _generate_investigation_prompt(pattern) if False else "",
            "evidence": pattern["evidence"][:15],
        }
        new_vector_entries.append((new_vec, pattern))
        vectors_created += 1

# Generate investigation prompts for new vectors
def generate_investigation_prompt(pattern):
    ptype = pattern["pattern_type"]
    sample = pattern["sample_text"][:100]
    if ptype == "open_recurrence":
        return f"This open item recurs across {pattern['n_sessions']} sessions: '{sample}'. Is this unresolved work, a tracking failure, or intentional deferral?"
    elif ptype == "workaround_churn":
        return f"This activity pattern repeats across {pattern['n_sessions']} sessions ({pattern['n_occurrences']} occurrences): '{sample}'. Is this a workaround that should be automated or eliminated?"
    elif ptype == "reopened_decision":
        return f"This decision appears in {pattern['n_sessions']} separate sessions: '{sample}'. Was the decision reversed, or is there unresolved tension?"
    return f"Pattern detected: '{sample}'"

# Fix investigation prompts
for new_vec, pattern in new_vector_entries:
    new_vec["investigation_prompt"] = generate_investigation_prompt(pattern)

# ── Step 6: Write results ───────────────────────────────────────────

# 6a: Write vectors.jsonl
with open(VECTORS_FILE, "w") as f:
    for vec in existing_vectors:
        f.write(json.dumps(vec, ensure_ascii=False) + "\n")
    for new_vec, _ in new_vector_entries:
        f.write(json.dumps(new_vec, ensure_ascii=False) + "\n")

print(f"\nVectors updated: {vectors_updated}")
print(f"Vectors created: {vectors_created}")
if updated_vector_ids:
    print(f"  Updated IDs: {', '.join(updated_vector_ids)}")

# 6b: Update scan_state.json
newest_session = session_ids_processed[-1] if session_ids_processed else "unknown"
scan_state = {
    "last_scan_session": newest_session,
    "last_scan_at": now_iso,
    "total_sessions_scanned": len(session_ids_processed),
    "note": f"Full scan: {len(session_ids_processed)} sessions, {total_points} points. {vectors_created} new vectors, {vectors_updated} existing updated. {len(patterns)} patterns met thresholds.",
    "mission_statement": "Ensure completeness of agreed ideas — track commitment fulfillment, feed work queue, build urgency for future work",
    "data_sources": [
        {"source": "WAI-Spoke/sessions/*/track.jsonl", "fields_used": ["decisions", "insights", "open", "activity"], "fields_needed": ["decisions"], "adequacy": "good"},
        {"source": "WAI-Spoke/lugs/bytype/*/open/*.json", "fields_used": ["title", "status", "created_at"], "fields_needed": ["resolved_at"], "adequacy": "good"},
        {"source": "WAI-Spoke/advisors/historian/vectors.jsonl", "fields_used": ["patterns"], "fields_needed": [], "adequacy": "good"}
    ],
    "self_sharpening_log": []
}

with open(SCAN_STATE_FILE, "w") as f:
    json.dump(scan_state, f, indent=2, ensure_ascii=False)
    f.write("\n")

# 6c: Append pass record
pass_record = {
    "id": f"pass-{scan_ts}",
    "timestamp": now_iso,
    "sessions_reviewed": session_ids_processed,
    "points_reviewed": total_points,
    "batch_strategy": "full-scan",
    "batch_size": total_points,
    "vectors_created": vectors_created,
    "vectors_confirmed": vectors_updated,
    "nudges_proposed": 0,
    "protocol_proposals": 0,
    "patterns_detected": len(all_clusters),
    "patterns_surfaced": len(patterns),
}

with open(PASSES_FILE, "a") as f:
    f.write(json.dumps(pass_record, ensure_ascii=False) + "\n")

# ── Step 7: Report ──────────────────────────────────────────────────
print("\n" + "=" * 60)
print("HISTORIAN SCAN REPORT")
print("=" * 60)
print(f"Sessions scanned:    {len(session_ids_processed)}")
print(f"Track points:        {total_points}")
print(f"Items extracted:     {len(items)}")
print(f"Items after filter:  {len(filtered_items)}")
print(f"Clusters found:      {len(all_clusters)}")
print(f"Patterns surfaced:   {len(patterns)}")
print(f"Vectors created:     {vectors_created}")
print(f"Vectors updated:     {vectors_updated}")
print(f"Newest session:      {newest_session}")

if new_vector_entries:
    print(f"\n--- New Vectors ---")
    for new_vec, pattern in new_vector_entries:
        print(f"\n  [{new_vec['id']}] ({new_vec['pattern_type']})")
        print(f"  Description: {new_vec['description'][:120]}")
        print(f"  Sessions: {pattern['n_sessions']}, Occurrences: {pattern['n_occurrences']}")
        print(f"  Prompt: {new_vec['investigation_prompt'][:150]}")

if updated_vector_ids:
    print(f"\n--- Updated Vectors ---")
    for vid in updated_vector_ids:
        vec = next(v for v in existing_vectors if v["id"] == vid)
        print(f"  [{vid}] occurrences={vec['occurrences']}, last_seen={vec['last_seen']}")

# Top 3 by occurrence count
print(f"\n--- Top 3 Patterns by Occurrence ---")
sorted_patterns = sorted(patterns, key=lambda p: p["n_occurrences"], reverse=True)
for i, p in enumerate(sorted_patterns[:3], 1):
    print(f"\n  #{i}: {p['pattern_type']} — {p['n_occurrences']} occurrences across {p['n_sessions']} sessions")
    print(f"      Sample: {p['sample_text'][:120]}")
    prompt = generate_investigation_prompt(p)
    print(f"      Prompt: {prompt[:150]}")

print(f"\n{'=' * 60}")
print("Scan complete. Files written:")
print(f"  {VECTORS_FILE}")
print(f"  {SCAN_STATE_FILE}")
print(f"  {PASSES_FILE}")
print(f"{'=' * 60}")
