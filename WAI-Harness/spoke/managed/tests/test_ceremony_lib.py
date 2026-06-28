"""test_ceremony_lib.py — P1 of initiative-optimize-ceremonies-v1.

The shared ceremony preamble (ceremony-lib.sh + ceremony_lib.py) must resolve the
same harness-mode-aware BASE/TOOLS that the ceremonies previously inlined.
"""
import os
import shutil
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.join(_HERE, "..", "shared")
_TOOLS = os.path.join(_HERE, "..", "tools")
sys.path.insert(0, _SHARED)

import ceremony_lib  # noqa: E402


def _v4_spoke(tmp):
    # a minimal v4-only spoke that carries the real managed tools (so wai_paths works)
    managed_tools = os.path.join(tmp, "WAI-Harness", "spoke", "managed", "tools")
    os.makedirs(managed_tools, exist_ok=True)
    for t in ("wai_paths.py",):
        shutil.copy2(os.path.join(_TOOLS, t), os.path.join(managed_tools, t))
    local = os.path.join(tmp, "WAI-Harness", "spoke", "local")
    os.makedirs(local, exist_ok=True)
    open(os.path.join(local, "WAI-State.json"), "w").write("{}")
    shutil.copy2(os.path.join(_SHARED, "ceremony-lib.sh"),
                 os.path.join(tmp, "WAI-Harness", "spoke", "managed", "shared_lib.sh"))
    # also place the lib at its canonical relative path for the sh test
    os.makedirs(os.path.join(tmp, "WAI-Harness", "spoke", "managed", "shared"), exist_ok=True)
    shutil.copy2(os.path.join(_SHARED, "ceremony-lib.sh"),
                 os.path.join(tmp, "WAI-Harness", "spoke", "managed", "shared", "ceremony-lib.sh"))
    return tmp


def test_py_resolves_v4(tmp_path):
    tmp = _v4_spoke(str(tmp_path))
    env = dict(os.environ, WAI_HARNESS_MODE="v4-only")
    # resolve_base runs wai_paths as a subprocess in cwd=tmp
    cur = os.getcwd()
    try:
        os.chdir(tmp)
        assert ceremony_lib.resolve_tools() == "WAI-Harness/spoke/managed/tools"
        base = ceremony_lib.resolve_base()
        assert base == "WAI-Harness/spoke/local", base
    finally:
        os.chdir(cur)


def test_py_falls_back_v3(tmp_path):
    # no WAI-Harness at all -> v3 fallback
    tmp = str(tmp_path)
    os.makedirs(os.path.join(tmp, "WAI-Spoke"), exist_ok=True)
    cur = os.getcwd()
    try:
        os.chdir(tmp)
        assert ceremony_lib.resolve_base() == "WAI-Spoke"
    finally:
        os.chdir(cur)


def test_sh_ceremony_init_v4(tmp_path):
    tmp = _v4_spoke(str(tmp_path))
    script = (
        "source WAI-Harness/spoke/managed/shared/ceremony-lib.sh && "
        "ceremony_init && echo \"$BASE|$TOOLS\""
    )
    r = subprocess.run(["bash", "-c", script], cwd=tmp,
                       env=dict(os.environ, WAI_HARNESS_MODE="v4-only"),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = r.stdout.strip()
    assert out == "WAI-Harness/spoke/local|WAI-Harness/spoke/managed/tools", out
