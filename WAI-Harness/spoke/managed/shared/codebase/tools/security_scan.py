#!/usr/bin/env python3
"""
security_scan.py — Static scanner for prompt injection and destructive directives.

Scans advisor context_prompt.md files, teachings, and lug _behavior_directive fields
for blacklisted patterns (block-level) and warning patterns (warn-level).

Default policy: warn-only for first release. Upgrade path to block is noted in config.

Usage:
    python3 tools/security_scan.py --target <file_or_dir> [--config config/security_scan_patterns.json]
"""

import json
import re
import os
import sys
import argparse
import fnmatch

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DEFAULT_CONFIG = os.path.join(PROJECT_ROOT, "config", "security_scan_patterns.json")


def load_patterns(config_path=None):
    if config_path is None:
        config_path = DEFAULT_CONFIG
    if not os.path.isabs(config_path):
        config_path = os.path.join(PROJECT_ROOT, config_path)
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config


def scan_file(file_path, config):
    """Scan a single file for blacklisted and warning patterns."""
    findings = []

    # Check excluded paths
    rel_path = os.path.relpath(file_path, PROJECT_ROOT)
    for excluded_path in config.get('excluded_paths', []):
        if fnmatch.fnmatch(rel_path, excluded_path) or excluded_path in rel_path:
            return findings

    try:
        with open(file_path, 'r', errors='replace') as f:
            lines = f.read().splitlines()

        for i, line in enumerate(lines):
            for pattern in config.get('blacklisted_patterns', []):
                if re.search(re.escape(pattern), line, re.IGNORECASE):
                    findings.append({
                        "severity": "block",
                        "pattern": pattern,
                        "file": file_path,
                        "line": i + 1,
                        "message": f"Blacklisted pattern '{pattern}' found."
                    })
            for pattern in config.get('warning_patterns', []):
                if re.search(re.escape(pattern), line, re.IGNORECASE):
                    findings.append({
                        "severity": "warn",
                        "pattern": pattern,
                        "file": file_path,
                        "line": i + 1,
                        "message": f"Warning pattern '{pattern}' found."
                    })
    except Exception as e:
        findings.append({
            "severity": "error",
            "file": file_path,
            "message": f"Error reading file: {e}"
        })
    return findings


def scan_json_behavior_directive(file_path, config):
    """Scan _behavior_directive field in a JSON file."""
    findings = []
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)

        # Handle both dict and list of dicts
        items = [data] if isinstance(data, dict) else data if isinstance(data, list) else []

        for item in items:
            if not isinstance(item, dict):
                continue
            directive = item.get('_behavior_directive', '')
            if isinstance(directive, dict):
                directive = json.dumps(directive)
            if not isinstance(directive, str):
                continue

            for pattern in config.get('blacklisted_patterns', []):
                if re.search(re.escape(pattern), directive, re.IGNORECASE):
                    findings.append({
                        "severity": "block",
                        "pattern": pattern,
                        "file": file_path,
                        "context": "_behavior_directive",
                        "message": f"Blacklisted pattern '{pattern}' found in _behavior_directive."
                    })
            for pattern in config.get('warning_patterns', []):
                if re.search(re.escape(pattern), directive, re.IGNORECASE):
                    findings.append({
                        "severity": "warn",
                        "pattern": pattern,
                        "file": file_path,
                        "context": "_behavior_directive",
                        "message": f"Warning pattern '{pattern}' found in _behavior_directive."
                    })
    except (json.JSONDecodeError, FileNotFoundError) as e:
        findings.append({
            "severity": "error",
            "file": file_path,
            "message": f"Error processing JSON: {e}"
        })
    return findings


def matches_scan_target(rel_path, scan_targets):
    """Check if a relative path matches any scan target glob pattern."""
    for target_pattern in scan_targets:
        if fnmatch.fnmatch(rel_path, target_pattern):
            return True
    return False


def scan_target(target_path, patterns_config):
    """Scan a file or directory, respecting scan_targets from config."""
    all_findings = []
    scan_targets = patterns_config.get('scan_targets', [])

    if os.path.isfile(target_path):
        rel_path = os.path.relpath(target_path, PROJECT_ROOT)
        if target_path.endswith('.json'):
            all_findings.extend(scan_json_behavior_directive(target_path, patterns_config))
        all_findings.extend(scan_file(target_path, patterns_config))
        return all_findings

    if os.path.isdir(target_path):
        for root, _, files in os.walk(target_path):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, PROJECT_ROOT)

                if scan_targets and not matches_scan_target(rel_path, scan_targets):
                    # If scan_targets specified, only scan matching files
                    # But if no scan_targets, scan everything in the directory
                    continue

                if file.endswith('.json'):
                    all_findings.extend(scan_json_behavior_directive(full_path, patterns_config))
                all_findings.extend(scan_file(full_path, patterns_config))
    else:
        print(f"Error: Target '{target_path}' is not a valid file or directory.", file=sys.stderr)
        sys.exit(1)

    return all_findings


def main():
    parser = argparse.ArgumentParser(description="Security scanner for prompt injection and destructive directives.")
    parser.add_argument("--target", required=True, help="File or directory to scan.")
    parser.add_argument("--config", default=None, help="Path to the patterns config file.")
    args = parser.parse_args()

    patterns_config = load_patterns(args.config)
    all_findings = scan_target(args.target, patterns_config)

    if all_findings:
        print(json.dumps(all_findings, indent=2))
        block_found = any(f.get('severity') == 'block' for f in all_findings)
        if block_found:
            sys.exit(1)  # Block-level finding

    # No issues or only warnings — exit 0
    # Default policy: warn-only for first release.
    # Upgrade path: change to sys.exit(1) when pattern coverage is proven.
    if not all_findings:
        print("No issues found.")

    sys.exit(0)


if __name__ == "__main__":
    main()
