import json
from pathlib import Path

import pytest

from lifecycle.flows import FLOW_DIR, load_flows, parse_flow, validate
from lifecycle.specdoc import DOC_DIR, load_raw_flows, render_spec
from lifecycle.templates import template_names


def test_shipped_flows_load_and_validate():
    flows = load_flows()
    assert set(flows) == {"welcome", "abandoned_cart", "winback", "onboarding"}


def _base():
    return {"id": "x", "name": "x", "trigger": {"event": "signup"}, "start": "a",
            "nodes": {"a": {"type": "delay", "hours": 1, "next": "b"}, "b": {"type": "exit"}}}


def test_validation_catches_problems():
    t = template_names()
    assert validate(parse_flow(_base()), t) == []
    d = _base(); d["nodes"]["a"]["next"] = "zzz"
    assert any("unknown node" in e for e in validate(parse_flow(d), t))
    d = _base(); d["nodes"]["c"] = {"type": "exit"}
    assert any("unreachable" in e for e in validate(parse_flow(d), t))
    d = _base(); d["nodes"]["b"] = {"type": "delay", "hours": 1, "next": "a"}
    assert any("cycle" in e for e in validate(parse_flow(d), t))
    d = _base(); d["nodes"]["b"] = {"type": "send", "template": "nope"}
    assert any("unknown template" in e for e in validate(parse_flow(d), t))
    d = _base(); d["nodes"]["a"]["hours"] = 0
    assert any("> 0" in e for e in validate(parse_flow(d), t))


def test_load_flows_rejects_invalid(tmp_path):
    bad = _base(); bad["nodes"]["a"]["next"] = "zzz"
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        load_flows(tmp_path)


def test_committed_specs_match_generator():
    for f in load_raw_flows():
        committed = (DOC_DIR / f"{f.id}.md").read_text()
        assert committed == render_spec(f), f"docs/flows/{f.id}.md is stale: run python -m lifecycle.specdoc --write"
        assert "Modeled, not deployed" in committed
