"""Acceptance proof: cutover_readiness.py — the retire-legacy gate."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import cutover_readiness as cr  # noqa: E402


def test_master_versioned(tmp_path):
    mw = tmp_path / "mywheel"; mw.mkdir()
    assert cr.check_master_versioned(str(mw))["ok"] is False  # no .git
    (mw / ".git").mkdir()
    assert cr.check_master_versioned(str(mw))["ok"] is True


def test_new_hub_serves_requires_registry_and_advisors(tmp_path):
    hub = tmp_path / "newhub"
    (hub / "managed").mkdir(parents=True)
    assert cr.check_new_hub_serves(str(hub))["ok"] is False          # empty skeleton
    (hub / "managed" / "hub-registry.json").write_text("{}")
    (hub / "managed" / "advisors" / "octo").mkdir(parents=True)
    assert cr.check_new_hub_serves(str(hub))["ok"] is True


def _install(tmp_path, name, hub_path, integrity="PASS", currency="CURRENT", activation="ACTIVE"):
    root = tmp_path / name
    (root / "WAI-Spoke").mkdir(parents=True)
    (root / "WAI-Spoke" / "WAI-State.json").write_text(json.dumps({"wheel": {"hub_path": hub_path}}))
    return {"install": str(root / "WAI-Harness"), "integrity": integrity,
            "currency": currency, "activation": activation, "parity": {}}


def test_assess_flags_old_hub_and_unwarmed(tmp_path):
    new_hub = str(tmp_path / "newhub"); old_hub = str(tmp_path / "oldhub")
    report = {"installs": [
        _install(tmp_path, "a", new_hub),                                   # good
        _install(tmp_path, "b", old_hub),                                   # on old hub
        _install(tmp_path, "c", new_hub, currency="STALE", activation="DORMANT"),  # not warmed
    ]}
    conds, detail = cr.assess(report, new_hub=new_hub, old_hub=old_hub)
    byname = {c["name"]: c for c in conds}
    assert byname["fleet_warmed"]["ok"] is False        # c not warmed
    assert byname["fleet_on_new_hub"]["ok"] is False     # b on old hub
    assert byname["no_legacy_refs"]["ok"] is False       # b
    assert detail["on_old_hub"] and len(detail["on_new_hub"]) == 2


def test_assess_all_green(tmp_path):
    new_hub = str(tmp_path / "newhub")
    report = {"installs": [_install(tmp_path, "a", new_hub), _install(tmp_path, "b", new_hub)]}
    conds, detail = cr.assess(report, new_hub=new_hub, old_hub=str(tmp_path / "oldhub"))
    assert all(c["ok"] for c in conds)
    assert detail["on_old_hub"] == [] and len(detail["warmed"]) == 2
