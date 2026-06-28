#!/usr/bin/env python3
"""secret_precommit_scan.py — block secrets from being committed (Fable MR-2).

The Fable 2026-06-12 review found secrets committed in 7 of ~11 owned projects, with the
identical root cause everywhere: no `.gitignore` discipline AND **zero pre-commit hooks in
the entire fleet**. This is the scanner half of the fix (the `.gitignore` baseline is MR-1).

Design:
  - If `gitleaks` is on PATH it runs FIRST (`gitleaks protect --staged`) — the comprehensive,
    actively-maintained ruleset. Its findings are authoritative.
  - Whether or not gitleaks is present, a focused built-in scan ALSO runs over the staged
    additions for the exact high-confidence secret CLASSES the review found (provider API
    keys, private-key blocks, cloud creds, tokens). This means the hook is useful TODAY,
    before anyone installs gitleaks, instead of being a no-op (a soft feature).
  - Placeholder-looking matches (<your-key>, EXAMPLE, REDACTED, xxxx) are not flagged.

This is a HIGH-CONFIDENCE baseline, not a guarantee: install gitleaks for full coverage.
Bypass an individual commit with `git commit --no-verify` (use sparingly).

Usage:
  python3 tools/secret_precommit_scan.py --staged        # scan staged additions (hook mode)
  python3 tools/secret_precommit_scan.py --paths a b      # scan specific files
  echo "...text..." | python3 tools/secret_precommit_scan.py --stdin
Exit: 0 clean | 1 secret(s) found | 2 error.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys

# (name, compiled regex). Patterns are deliberately specific so legitimate commits are not
# blocked by false positives — the cost of a noisy hook is that people disable it.
_PATTERNS = [
    ("Anthropic API key", re.compile(r"sk-ant-(?:api|admin)[0-9A-Za-z._-]{20,}")),
    ("OpenAI API key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9]{20,}T3BlbkFJ[A-Za-z0-9]{20,}")),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA)[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[0-9A-Za-z_]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("Stripe secret key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[0-9A-Za-z]{20,}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("Z.AI / GLM key", re.compile(r"\b[0-9a-f]{32}\.[0-9A-Za-z]{16}\b")),
    ("Supabase service_role JWT", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{30,}\.[A-Za-z0-9_-]{20,}")),
    ("Generic assigned secret", re.compile(
        r"(?i)(?:api[_-]?key|secret|passwd|password|token|access[_-]?key)['\"]?\s*[:=]\s*"
        r"['\"]([A-Za-z0-9+/_\-]{24,})['\"]")),
]

# A match whose secret-looking span contains any of these is treated as a placeholder, not a leak.
_PLACEHOLDER = re.compile(
    r"(?i)\b(?:your|example|sample|placeholder|redacted|changeme|dummy|fake|test[_-]?key|xxx+|\.\.\.|<[^>]+>)\b"
    r"|\bx{8,}\b|\*{4,}|0{8,}")


def _is_placeholder(span: str) -> bool:
    return bool(_PLACEHOLDER.search(span))


def scan_text(text: str, source: str = "<text>") -> list[dict]:
    """Return [{source, line, rule, match}] for high-confidence secrets in `text`.
    Core scanner — pure, no git/IO — so it is directly unit-testable."""
    findings = []
    for lineno, line in enumerate(text.splitlines(), 1):
        # Inline escape hatch (gitleaks convention) for deliberate fixtures / known-safe literals.
        if "gitleaks:allow" in line or "pragma: allowlist secret" in line:
            continue
        for rule, rx in _PATTERNS:
            for m in rx.finditer(line):
                span = m.group(0)
                if _is_placeholder(line):
                    continue
                findings.append({
                    "source": source,
                    "line": lineno,
                    "rule": rule,
                    # redact the middle so the finding itself is safe to print/log
                    "match": span[:6] + "…" + span[-4:] if len(span) > 14 else span[:3] + "…",
                })
    return findings


def _staged_additions() -> list[tuple[str, str]]:
    """Return [(path, added_text)] for files staged in the index (added lines only)."""
    try:
        names = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True, text=True, check=True).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    out = []
    for path in names:
        try:
            diff = subprocess.run(
                ["git", "diff", "--cached", "-U0", "--", path],
                capture_output=True, text=True, check=True).stdout
        except subprocess.CalledProcessError:
            continue
        added = "\n".join(
            ln[1:] for ln in diff.splitlines()
            if ln.startswith("+") and not ln.startswith("+++"))
        if added:
            out.append((path, added))
    return out


def _run_gitleaks() -> tuple[bool, str]:
    """(ran, output). Runs gitleaks over staged content if available; ran=False if absent."""
    if not shutil.which("gitleaks"):
        return False, ""
    r = subprocess.run(["gitleaks", "protect", "--staged", "--redact", "-v"],
                       capture_output=True, text=True)
    # gitleaks exits non-zero when it finds leaks
    return True, (r.stdout + r.stderr) if r.returncode != 0 else ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pre-commit secret scanner (Fable MR-2).")
    ap.add_argument("--staged", action="store_true", help="scan git staged additions (hook mode)")
    ap.add_argument("--paths", nargs="*", help="scan specific files")
    ap.add_argument("--stdin", action="store_true", help="scan text from stdin")
    args = ap.parse_args(argv)

    findings: list[dict] = []
    gitleaks_hit = ""

    if args.staged:
        ran, out = _run_gitleaks()
        if ran and out:
            gitleaks_hit = out
        for path, added in _staged_additions():
            findings += scan_text(added, source=path)
    if args.paths:
        for p in args.paths:
            try:
                findings += scan_text(open(p, encoding="utf-8", errors="ignore").read(), source=p)
            except OSError as e:
                print(f"secret-scan: cannot read {p}: {e}", file=sys.stderr)
    if args.stdin:
        findings += scan_text(sys.stdin.read(), source="<stdin>")

    if not (args.staged or args.paths or args.stdin):
        ap.print_help()
        return 2

    if gitleaks_hit:
        print("✖ gitleaks flagged staged content:\n" + gitleaks_hit.strip(), file=sys.stderr)
    if findings:
        print("✖ secret-scan: high-confidence secret(s) in staged content — commit BLOCKED:",
              file=sys.stderr)
        for f in findings:
            print(f"    {f['source']}:{f['line']}  [{f['rule']}]  {f['match']}", file=sys.stderr)
    if gitleaks_hit or findings:
        print("  Remove the secret (and rotate it if it was ever real). "
              "Override with `git commit --no-verify` only if this is a false positive.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
