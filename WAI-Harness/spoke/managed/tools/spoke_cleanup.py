#!/usr/bin/env python3
"""WAI Spoke Cleanup — Restructure WAI-Spoke/ into clean folder hierarchy.

Structure created:
  WAI-Spoke/lugs/
    incoming/                        — inbound deliveries
    outgoing/                        — outbound deliveries
    reference/                       — reference docs
    bytype/
      epic/{open,in_progress,completed}/
      task/{open,in_progress,completed}/
      feature/{open,in_progress,completed}/
      implementation/{in_progress,completed}/
      signal/{undelivered,delivered}/
      session-summary/               — all completed, no status subfolder
      bug/{open,in_progress,completed}/
      other/{open,completed}/        — rare types (policy, learning, etc.)

  WAI-Spoke/sessions/
    session-YYYYMMDD-HHMM/track.jsonl  — each track in its own session dir

  WAI-Spoke/archive/
    epic-workspaces/                 — legacy epic BRIEF/plan folders
    lug-workspaces/                  — legacy lug artifact folders
    loose-lugs/                      — stray files from lugs/ root

Phases:
  1. Remove retired WAI-Lugs.jsonl + backup
  2. Organize loose track files into session dirs
  3. Restructure lugs into bytype/{type}/{status}/ hierarchy
  4. Consolidate legacy epic-*/lug-* folders to archive
  5. Route loose files in lugs/ root
  6. Update WAI-LugIndex.jsonl
  7. Report final state

Usage:
  python3 tools/spoke_cleanup.py --dry-run
  python3 tools/spoke_cleanup.py
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lug_utils import get_lug_id, get_lug_type, get_lug_status, get_lug_title

SPOKE_DIR = "WAI-Spoke"
LUGS_DIR = os.path.join(SPOKE_DIR, "lugs")
BYTYPE_DIR = os.path.join(LUGS_DIR, "bytype")
ACTIVE_FILE = os.path.join(LUGS_DIR, "active", "WAI-Lugs-active.jsonl")
INDEX_FILE = os.path.join(SPOKE_DIR, "WAI-LugIndex.jsonl")
SESSIONS_DIR = os.path.join(SPOKE_DIR, "sessions")
ARCHIVE_DIR = os.path.join(SPOKE_DIR, "archive")

# Types that get their own top-level folder in bytype/
PROMOTED_TYPES = {"epic", "task", "feature", "bug", "implementation", "signal", "session-summary"}

# Status folders per type
STATUS_FOLDERS = {
    "epic":           ["open", "in_progress", "completed"],
    "task":           ["open", "in_progress", "completed"],
    "feature":        ["open", "in_progress", "completed"],
    "bug":            ["open", "in_progress", "completed"],
    "implementation": ["in_progress", "completed"],
    "signal":         ["undelivered", "delivered"],
    "other":          ["open", "completed"],
    # session-summary has no status subfolders — they're all completed
}

# Map raw lug statuses to folder names
STATUS_MAP = {
    # Active
    "open": "open", "o": "open",
    "in_progress": "in_progress", "p": "in_progress", "in-progress": "in_progress",
    # Completed
    "completed": "completed", "c": "completed", "closed": "completed",
    "resolved": "completed", "implemented": "completed", "archived": "completed",
    "published": "completed", "analyzed": "completed", "drafted": "completed",
    "skipped": "completed", "accepted": "completed",
    # Signal-specific
    "delivered": "delivered",
    # Edge cases
    "ready_to_implement": "open", "ready_for_recheck": "open",
    "proposed": "open", "deferred": "open",
    "unknown": "completed",
}

# Regex for track filename date extraction
TRACK_DATE_RE = re.compile(r"track_?(\d{8})[-_]?(\d{4})?")
WAI_TRACK_RE = re.compile(r"WAI_Track-(\d{8})-(\d{4})")

KEY_MAP = {"i": "id", "ty": "type", "t": "title", "s": "status", "ca": "created_at", "gb": "created_by"}

dry_run = False


def log(msg):
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"  {prefix}{msg}")


def ensure_dir(path):
    if not os.path.exists(path):
        if not dry_run:
            os.makedirs(path, exist_ok=True)


def move_file(src, dst):
    ensure_dir(os.path.dirname(dst))
    if not dry_run:
        shutil.move(src, dst)
    log(f"move {src} -> {dst}")


def remove_file(path):
    size = os.path.getsize(path) if os.path.exists(path) else 0
    if not dry_run:
        os.remove(path)
    log(f"delete {path} ({size:,} bytes)")


def remove_dir_if_empty(path):
    if os.path.isdir(path) and not os.listdir(path):
        if not dry_run:
            os.rmdir(path)
        log(f"rmdir (empty) {path}")


def classify_type(lug_type):
    """Return the bytype folder name for a lug type."""
    if lug_type in PROMOTED_TYPES:
        return lug_type
    return "other"


def classify_status(lug_type, raw_status):
    """Return the status subfolder name."""
    folder_type = classify_type(lug_type)

    if folder_type == "session-summary":
        return None  # No status subfolder

    if folder_type == "signal":
        # Signals: undelivered (open/in_progress) or delivered (everything else)
        mapped = STATUS_MAP.get(raw_status, "delivered")
        if mapped in ("open", "in_progress"):
            return "undelivered"
        return "delivered"

    mapped = STATUS_MAP.get(raw_status, "completed")

    # Validate against allowed statuses for this type
    allowed = STATUS_FOLDERS.get(folder_type, ["open", "completed"])
    if mapped in allowed:
        return mapped
    # Fallback: active statuses → open, others → completed
    if mapped in ("open", "in_progress"):
        return "open" if "open" in allowed else allowed[0]
    return "completed" if "completed" in allowed else allowed[-1]


def lug_dest_path(lug_type, status, lug_id):
    """Compute destination path for a lug."""
    type_folder = classify_type(lug_type)
    status_folder = classify_status(lug_type, status)
    safe_id = lug_id.replace("/", "-").replace("\\", "-")

    if status_folder:
        return os.path.join(BYTYPE_DIR, type_folder, status_folder, f"{safe_id}.json")
    else:
        return os.path.join(BYTYPE_DIR, type_folder, f"{safe_id}.json")


# ─── Phase 1: Remove retired files ───

def phase_1():
    print("\n=== Phase 1: Remove retired WAI-Lugs.jsonl ===")
    count = 0
    for name in ["WAI-Lugs.jsonl", "WAI-Lugs.jsonl.pre-diet-backup"]:
        path = os.path.join(SPOKE_DIR, name)
        if os.path.exists(path):
            remove_file(path)
            count += 1
    if count == 0:
        log("Already clean")
    return count


# ─── Phase 2: Organize loose tracks ───

def phase_2():
    print("\n=== Phase 2: Move loose track files into session dirs ===")
    count = 0
    if not os.path.isdir(SESSIONS_DIR):
        log("No sessions directory")
        return 0

    for filename in sorted(os.listdir(SESSIONS_DIR)):
        filepath = os.path.join(SESSIONS_DIR, filename)
        if not os.path.isfile(filepath):
            continue

        # Delete empty files
        if os.path.getsize(filepath) == 0:
            remove_file(filepath)
            count += 1
            continue

        # Extract date
        date_key = None
        m = TRACK_DATE_RE.search(filename)
        if m:
            date_key = f"{m.group(1)}-{m.group(2) or '0000'}"
        else:
            m = WAI_TRACK_RE.search(filename)
            if m:
                date_key = f"{m.group(1)}-{m.group(2)}"

        session_dir = os.path.join(SESSIONS_DIR, f"session-{date_key}") if date_key else os.path.join(SESSIONS_DIR, "unsorted-tracks")
        dst = os.path.join(session_dir, filename)

        if not os.path.exists(dst):
            move_file(filepath, dst)
            count += 1
        else:
            log(f"skip {filename} — already at destination")

    if count == 0:
        log("No loose tracks")
    return count


# ─── Phase 3: Restructure lugs into bytype/{type}/{status}/ ───

def phase_3():
    print("\n=== Phase 3: Restructure lugs into bytype/ hierarchy ===")
    count = 0

    # Create bytype folder structure
    for type_name, statuses in STATUS_FOLDERS.items():
        for status in statuses:
            ensure_dir(os.path.join(BYTYPE_DIR, type_name, status))
    ensure_dir(os.path.join(BYTYPE_DIR, "session-summary"))

    # A) Decant active JSONL
    if os.path.exists(ACTIVE_FILE):
        print("  --- Decanting active lugs ---")
        with open(ACTIVE_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    lug = json.loads(line)
                except json.JSONDecodeError:
                    continue

                lug_id = get_lug_id(lug)
                lug_type = get_lug_type(lug)
                status = get_lug_status(lug)
                dst = lug_dest_path(lug_type, status, lug_id)

                if not os.path.exists(dst):
                    ensure_dir(os.path.dirname(dst))
                    if not dry_run:
                        with open(dst, "w") as out:
                            json.dump(lug, out, ensure_ascii=False, indent=2)
                    log(f"decant [{status}] {lug_id} -> {dst}")
                    count += 1

        # Remove active file and directory
        if not dry_run:
            os.remove(ACTIVE_FILE)
            remove_dir_if_empty(os.path.dirname(ACTIVE_FILE))
        log(f"delete {ACTIVE_FILE} (decanted)")

    # B) Move archived lugs from old type folders
    OLD_TYPE_DIRS = set()
    for entry in sorted(os.listdir(LUGS_DIR)):
        entry_path = os.path.join(LUGS_DIR, entry)
        if not os.path.isdir(entry_path):
            continue
        # Skip operational and new structure dirs
        if entry in ("incoming", "outgoing", "reference", "active", "bytype"):
            continue
        # Skip legacy epic-*/lug-* folders (handled in phase 4)
        if entry.startswith("epic-") or entry.startswith("lug-"):
            continue

        # This is an old type folder from the first migration
        json_files = [f for f in os.listdir(entry_path) if f.endswith(".json")]
        if not json_files:
            continue

        OLD_TYPE_DIRS.add(entry)
        for fname in sorted(json_files):
            fpath = os.path.join(entry_path, fname)
            try:
                with open(fpath) as f:
                    lug = json.load(f)
            except (json.JSONDecodeError, OSError):
                log(f"WARNING: skipping unreadable {fpath}")
                continue

            lug_id = get_lug_id(lug)
            lug_type = get_lug_type(lug)
            status = get_lug_status(lug)
            dst = lug_dest_path(lug_type, status, lug_id)

            if not os.path.exists(dst) and fpath != dst:
                ensure_dir(os.path.dirname(dst))
                move_file(fpath, dst)
                count += 1

        # Remove old type folder — force-clean remaining dupes
        if os.path.isdir(entry_path):
            remaining = [f for f in os.listdir(entry_path) if f.endswith(".json")]
            for fname in remaining:
                fpath = os.path.join(entry_path, fname)
                # These are duplicates already moved — safe to remove
                if not dry_run:
                    os.remove(fpath)
                log(f"remove dupe {fpath}")
            remove_dir_if_empty(entry_path)

    print(f"  --- Restructured {count} lugs ---")
    return count


# ─── Phase 4: Consolidate legacy folders ───

def phase_4():
    print("\n=== Phase 4: Archive legacy epic-*/lug-* folders ===")
    count = 0

    for entry in sorted(os.listdir(LUGS_DIR)):
        entry_path = os.path.join(LUGS_DIR, entry)
        if not os.path.isdir(entry_path):
            continue

        if entry.startswith("epic-"):
            dst = os.path.join(ARCHIVE_DIR, "epic-workspaces", entry)
        elif entry.startswith("lug-"):
            dst = os.path.join(ARCHIVE_DIR, "lug-workspaces", entry)
        else:
            continue

        if not os.path.exists(dst):
            move_file(entry_path, dst)
            count += 1

    if count == 0:
        log("No legacy folders")
    return count


# ─── Phase 5: Route loose files ───

def phase_5():
    print("\n=== Phase 5: Route loose files in lugs/ root ===")
    count = 0

    for entry in sorted(os.listdir(LUGS_DIR)):
        entry_path = os.path.join(LUGS_DIR, entry)
        if not os.path.isfile(entry_path):
            continue
        if entry == "README.md":
            continue

        dst = os.path.join(ARCHIVE_DIR, "loose-lugs", entry)
        move_file(entry_path, dst)
        count += 1

    if count == 0:
        log("No loose files")
    return count


# ─── Phase 6: Regenerate index ───

def phase_6():
    print("\n=== Phase 6: Regenerate WAI-LugIndex.jsonl ===")
    entries = []

    if not os.path.isdir(BYTYPE_DIR):
        log("No bytype/ directory — skipping index")
        return 0

    for type_folder in sorted(os.listdir(BYTYPE_DIR)):
        type_path = os.path.join(BYTYPE_DIR, type_folder)
        if not os.path.isdir(type_path):
            continue

        # Check for status subfolders or direct .json files
        for sub in sorted(os.listdir(type_path)):
            sub_path = os.path.join(type_path, sub)

            if os.path.isdir(sub_path):
                # Status subfolder
                for fname in sorted(os.listdir(sub_path)):
                    if not fname.endswith(".json"):
                        continue
                    fpath = os.path.join(sub_path, fname)
                    try:
                        with open(fpath) as f:
                            lug = json.load(f)
                        entries.append({
                            "id": get_lug_id(lug),
                            "type": get_lug_type(lug),
                            "status": get_lug_status(lug),
                            "title": get_lug_title(lug),
                            "folder": f"bytype/{type_folder}/{sub}",
                            "created_at": lug.get("created_at") or lug.get("ca") or "",
                        })
                    except (json.JSONDecodeError, OSError):
                        pass

            elif sub.endswith(".json"):
                # Direct file (session-summary, no status subfolder)
                try:
                    with open(sub_path) as f:
                        lug = json.load(f)
                    entries.append({
                        "id": get_lug_id(lug),
                        "type": get_lug_type(lug),
                        "status": get_lug_status(lug),
                        "title": get_lug_title(lug),
                        "folder": f"bytype/{type_folder}",
                        "created_at": get_field(lug, "created_at", "ca"),
                    })
                except (json.JSONDecodeError, OSError):
                    pass

    if dry_run:
        log(f"Would write {len(entries)} entries to {INDEX_FILE}")
    else:
        with open(INDEX_FILE, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        log(f"Wrote {len(entries)} entries to {INDEX_FILE}")

    return len(entries)


# ─── Phase 7: Report ───

def phase_7():
    print("\n=== Final State ===")

    # bytype summary
    if os.path.isdir(BYTYPE_DIR):
        for type_folder in sorted(os.listdir(BYTYPE_DIR)):
            type_path = os.path.join(BYTYPE_DIR, type_folder)
            if not os.path.isdir(type_path):
                continue
            counts = {}
            for sub in os.listdir(type_path):
                sub_path = os.path.join(type_path, sub)
                if os.path.isdir(sub_path):
                    n = len([f for f in os.listdir(sub_path) if f.endswith(".json")])
                    if n:
                        counts[sub] = n
                elif sub.endswith(".json"):
                    counts["(root)"] = counts.get("(root)", 0) + 1
            if counts:
                parts = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
                print(f"  bytype/{type_folder}/  [{parts}]")

    # Operational folders
    for name in ["incoming", "outgoing", "reference"]:
        path = os.path.join(LUGS_DIR, name)
        if os.path.isdir(path):
            n = len(os.listdir(path))
            print(f"  {name}/  [{n} items]")

    # Sessions
    if os.path.isdir(SESSIONS_DIR):
        dirs = [d for d in os.listdir(SESSIONS_DIR) if os.path.isdir(os.path.join(SESSIONS_DIR, d))]
        loose = [f for f in os.listdir(SESSIONS_DIR) if os.path.isfile(os.path.join(SESSIONS_DIR, f))]
        print(f"  sessions/  [{len(dirs)} dirs, {len(loose)} loose files]")

    # Retired files
    for name in ["WAI-Lugs.jsonl", "WAI-Lugs.jsonl.pre-diet-backup"]:
        if os.path.exists(os.path.join(SPOKE_DIR, name)):
            print(f"  WARNING: retired {name} still exists")

    # Index
    if os.path.exists(INDEX_FILE):
        count = sum(1 for line in open(INDEX_FILE) if line.strip())
        size = os.path.getsize(INDEX_FILE)
        print(f"  WAI-LugIndex.jsonl  [{count} entries, {size:,} bytes]")


def main():
    global dry_run
    parser = argparse.ArgumentParser(description="WAI Spoke Cleanup — restructure WAI-Spoke/ into clean folder hierarchy.")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    dry_run = parser.parse_args().dry_run

    print(f"=== SPOKE CLEANUP {'(DRY RUN)' if dry_run else ''} ===")

    total = 0
    total += phase_1()
    total += phase_2()
    total += phase_3()
    total += phase_4()
    total += phase_5()
    phase_6()

    if not dry_run:
        phase_7()

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Total actions: {total}")


if __name__ == "__main__":
    main()
