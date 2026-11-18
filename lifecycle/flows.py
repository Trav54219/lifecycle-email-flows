"""Flow definitions: loading from JSON and structural validation."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .templates import template_names

FLOW_DIR = Path(__file__).resolve().parent.parent / "flows"
NODE_TYPES = {"delay", "send", "branch", "exit"}


@dataclass
class Flow:
    id: str
    name: str
    description: str
    trigger_event: str
    trigger_filter: dict | None
    reentry_hours: float | None  # None = once ever, 0 = every trigger event
    exit_events: list[str]
    allow_dormant: bool
    start: str
    nodes: dict[str, dict]


def _successors(node: dict) -> list[str]:
    t = node["type"]
    if t in ("delay", "send"):
        return [node["next"]] if node.get("next") else []
    if t == "branch":
        return [node["yes"], node["no"]]
    return []


def validate(flow: Flow, templates: set[str]) -> list[str]:
    errs = []
    if flow.start not in flow.nodes:
        errs.append(f"{flow.id}: start node '{flow.start}' missing")
        return errs
    for nid, n in flow.nodes.items():
        if n.get("type") not in NODE_TYPES:
            errs.append(f"{flow.id}.{nid}: bad type {n.get('type')}")
            continue
        for s in _successors(n):
            if s not in flow.nodes:
                errs.append(f"{flow.id}.{nid}: points to unknown node '{s}'")
        if n["type"] == "delay" and not n.get("hours", 0) > 0:
            errs.append(f"{flow.id}.{nid}: delay must be > 0 hours")
        if n["type"] == "send" and n.get("template") not in templates:
            errs.append(f"{flow.id}.{nid}: unknown template '{n.get('template')}'")
        if n["type"] == "branch" and "condition" not in n:
            errs.append(f"{flow.id}.{nid}: branch has no condition")
    if errs:
        return errs
    # reachability + cycle check (DFS with colors)
    color: dict[str, int] = {}

    def dfs(u: str):
        color[u] = 1
        for v in _successors(flow.nodes[u]):
            if color.get(v) == 1:
                errs.append(f"{flow.id}: cycle through '{v}'")
            elif v not in color:
                dfs(v)
        color[u] = 2

    dfs(flow.start)
    for nid in flow.nodes:
        if nid not in color:
            errs.append(f"{flow.id}: node '{nid}' unreachable from start")
    return errs


def parse_flow(d: dict) -> Flow:
    return Flow(
        id=d["id"], name=d["name"], description=d.get("description", ""),
        trigger_event=d["trigger"]["event"], trigger_filter=d["trigger"].get("filter"),
        reentry_hours=d.get("reentry_hours"), exit_events=d.get("exit_events", []),
        allow_dormant=d.get("allow_dormant", False), start=d["start"], nodes=d["nodes"],
    )


def load_flows(directory: Path = FLOW_DIR, templates: set[str] | None = None) -> dict[str, Flow]:
    templates = template_names() if templates is None else templates
    flows, errs = {}, []
    for p in sorted(directory.glob("*.json")):
        f = parse_flow(json.loads(p.read_text()))
        errs += validate(f, templates)
        flows[f.id] = f
    if errs:
        raise ValueError("invalid flows:\n" + "\n".join(errs))
    return flows
