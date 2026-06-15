#!/usr/bin/env python3
"""manifest_build.py — MD5 integrity manifest for the managed/ master (Stream F).

(impl-v4-harness-skeleton-v1) Walks spoke/managed/, computes an MD5 per file, and
writes MANIFEST.json: {harness_version, is_master, generated_at, files:{rel ->
{version, md5, owner}}}. This is the integrity contract that makes distribution
trustworthy two ways:

  - --verify reports any managed file whose on-disk MD5 no longer matches the
    recorded hash — i.e. an unauthorized edit to an agent-read-only file.
  - the recorded hashes are the basis for Basher's own-copy "upgrade-when-newer"
    check: a spoke pulls a managed file only when the master's hash differs.

build() and verify() are pure over an injected managed dir + manifest path, so
they are unit-testable and path-parameterized.

API:
  build(managed_dir, manifest_path, harness_version=..., now_iso=None) -> manifest
  verify(managed_dir, manifest_path) -> {"ok": bool, "mismatches": [...], "missing": [...], "new": [...]}
"""
import argparse
import hashlib
import json
import os
import sys

MANIFEST_NAME = "MANIFEST.json"
DEFAULT_OWNER = "basher"          # managed/ = Basher-distributed
DEFAULT_VERSION = "4.0.0-pre"
VERSION_FILE = "VERSION"          # single source of truth at the WAI-Harness root


def read_version(managed_dir, fallback=DEFAULT_VERSION):
    """Read the canonical harness version from the nearest VERSION file (walking up from
    managed_dir to the WAI-Harness root), so the manifest stamps the REAL version instead
    of a hardcoded constant. Bump that one file as the harness evolves. Fallback if absent."""
    d = os.path.abspath(managed_dir)
    for _ in range(4):  # managed -> spoke -> WAI-Harness -> (root)
        vf = os.path.join(d, VERSION_FILE)
        if os.path.isfile(vf):
            try:
                v = open(vf).read().strip()
                if v:
                    return v
            except OSError:
                pass
        d = os.path.dirname(d)
    return fallback

# build/runtime artifacts that are never source, never distributed, and whose
# bytes are non-deterministic (bytecode regenerates on import) — excluding them
# is what lets the master self-verify stably. Mirrors harness_upgrade._excluded.
_EXCLUDE_DIRS = {"__pycache__", ".pytest_cache", ".git"}
_EXCLUDE_SUFFIXES = (".pyc", ".pyo")
_EXCLUDE_NAMES = {".DS_Store"}


def _excluded(rel):
    parts = rel.replace(os.sep, "/").split("/")
    if any(p in _EXCLUDE_DIRS for p in parts):
        return True
    if rel.endswith(_EXCLUDE_SUFFIXES):
        return True
    return parts[-1] in _EXCLUDE_NAMES


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk_managed(managed_dir):
    """Relative paths of every file under managed/, EXCEPT the manifest itself."""
    out = {}
    for dirpath, dirs, files in os.walk(managed_dir):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIRS]  # prune cache dirs
        for name in files:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, managed_dir)
            if rel == MANIFEST_NAME:
                continue  # the manifest never hashes itself
            if _excluded(rel):
                continue  # never distribute bytecode/cache/OS cruft
            out[rel] = full
    return out


def build(managed_dir, manifest_path=None, harness_version=DEFAULT_VERSION, now_iso=None):
    """Compute MD5 per managed file and write MANIFEST.json. Idempotent: the same
    tree yields the same files map (only generated_at moves)."""
    manifest_path = manifest_path or os.path.join(managed_dir, MANIFEST_NAME)
    # preserve recorded owner/version where present
    prior = {}
    if os.path.exists(manifest_path):
        try:
            prior = json.load(open(manifest_path)).get("files", {})
        except (ValueError, OSError):
            prior = {}
    files = {}
    for rel, full in sorted(_walk_managed(managed_dir).items()):
        files[rel] = {"version": prior.get(rel, {}).get("version", harness_version),
                      "md5": _md5(full),
                      "owner": prior.get(rel, {}).get("owner", DEFAULT_OWNER)}
    manifest = {"harness_version": harness_version, "is_master": True,
                "generated_at": now_iso, "files": files}
    json.dump(manifest, open(manifest_path, "w"), indent=2)
    return manifest


def verify(managed_dir, manifest_path=None):
    """Compare on-disk managed files against the recorded manifest.
    mismatches = recorded file whose hash changed (unauthorized edit);
    missing = recorded file now absent; new = on-disk file not in the manifest."""
    manifest_path = manifest_path or os.path.join(managed_dir, MANIFEST_NAME)
    recorded = json.load(open(manifest_path)).get("files", {})
    on_disk = _walk_managed(managed_dir)
    mismatches, missing = [], []
    for rel, meta in recorded.items():
        full = on_disk.get(rel)
        if not full:
            missing.append(rel)
        elif _md5(full) != meta.get("md5"):
            mismatches.append(rel)
    new = [rel for rel in on_disk if rel not in recorded]
    return {"ok": not (mismatches or missing), "mismatches": mismatches,
            "missing": missing, "new": new}


def main(argv=None):
    ap = argparse.ArgumentParser(description="build or verify the managed/ MD5 manifest")
    ap.add_argument("managed_dir")
    ap.add_argument("--manifest-path", default=None)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--harness-version", default=None,
                    help="default reads the VERSION file at the WAI-Harness root (bump that to evolve)")
    ap.add_argument("--now-iso", default=None)
    a = ap.parse_args(argv)
    if a.verify:
        res = verify(a.managed_dir, a.manifest_path)
        print(json.dumps(res, indent=2))
        return 0 if res["ok"] else 1
    version = a.harness_version or read_version(a.managed_dir)
    m = build(a.managed_dir, a.manifest_path, version, a.now_iso)
    print(f"[manifest_build] {len(m['files'])} managed file(s) hashed -> "
          f"{a.manifest_path or os.path.join(a.managed_dir, MANIFEST_NAME)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
