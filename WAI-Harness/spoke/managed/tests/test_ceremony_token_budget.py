"""test_ceremony_token_budget.py — P4 of initiative-optimize-ceremonies-v1."""
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "tools"))
import ceremony_token_budget as ctb  # noqa: E402

_REAL_COMMANDS = os.path.join(_HERE, "..", ".claude", "commands")


def test_real_ceremonies_within_budget():
    """The shipped ceremonies must be within their post-optimization budgets."""
    rep = ctb.check(_REAL_COMMANDS)
    assert rep["ok"], "OVER budget: " + ", ".join(
        f"{e['file']} {e['lines']}/{e['budget']}" for e in rep["over"]
    )


def test_detects_over_budget(tmp_path):
    d = str(tmp_path)
    # write one budgeted file way over its ceiling
    name, budget = next(iter(ctb.BUDGETS.items()))
    with open(os.path.join(d, name), "w") as fh:
        fh.write("\n" * (budget + 50))
    rep = ctb.check(d)
    assert not rep["ok"]
    assert any(e["file"] == name for e in rep["over"])


def test_within_budget_passes(tmp_path):
    d = str(tmp_path)
    name, budget = next(iter(ctb.BUDGETS.items()))
    with open(os.path.join(d, name), "w") as fh:
        fh.write("\n" * (budget - 10))
    rep = ctb.check(d)
    assert rep["ok"], rep
