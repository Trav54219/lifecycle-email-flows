"""Generate canvas-style flow spec docs (markdown + mermaid) from flows/*.json.

These specs describe the flows as MODELED in this repo. They are not exports from, and have
not been deployed to, Klaviyo, Braze or Marketo.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .conditions import describe
from .engine import Policy
from .flows import FLOW_DIR, Flow, parse_flow

DOC_DIR = Path(__file__).resolve().parent.parent / "docs" / "flows"

BANNER = ("> **Modeled, not deployed.** This spec is generated from `flows/{id}.json` in this repo and "
          "laid out in the style of a Klaviyo flow / Braze Canvas export. It has never been imported "
          "into, or run on, any of those products.")

MAPPING = """## Rough platform mapping

| This engine | Klaviyo | Braze Canvas | Marketo |
|---|---|---|---|
| trigger event | metric-triggered flow | action-based entry | smart campaign trigger |
| delay | time delay | delay step | wait step (flow action) |
| branch | conditional split | decision split | choice step |
| send | email action | message step | send email |
| exit events | flow filter / exit on conversion | exit criteria | smart list filter in flow |
| re-entry | re-entry setting | entry re-eligibility window | "each person can run through the flow" |
"""


def _hours(h: float) -> str:
    n, unit = (h / 24, "day") if h % 24 == 0 and h >= 24 else (h, "hour")
    return f"{n:g} {unit}" + ("" if n == 1 else "s")


def _label(node_id: str, n: dict) -> str:
    if n["type"] == "delay":
        return f"Wait {_hours(n['hours'])}"
    if n["type"] == "send":
        return f"Send: {n['template']}"
    if n["type"] == "branch":
        return "Split: " + describe(n["condition"])
    return "End"


def render_spec(flow: Flow, policy: Policy | None = None) -> str:
    policy = policy or Policy()
    caps = ", ".join(f"max {m} per {w}h" for w, m in policy.caps)
    reentry = ("once per customer" if flow.reentry_hours is None else
               "every trigger event" if flow.reentry_hours == 0 else f"after {_hours(flow.reentry_hours)}")
    L = [f"# Flow spec: {flow.name}", "", BANNER.format(id=flow.id), "", flow.description, "",
         "## Entry and exit", "",
         "| Setting | Value |", "|---|---|",
         f"| Trigger event | `{flow.trigger_event}` |",
         f"| Trigger filter | {describe(flow.trigger_filter) if flow.trigger_filter else 'none'} |",
         f"| Re-entry | {reentry} |",
         f"| Exit events | {', '.join(f'`{e}`' for e in flow.exit_events) or 'none'} |",
         f"| Sends to dormant tier | {'yes' if flow.allow_dormant else 'no (sunset policy applies)'} |", "",
         "## Steps", "", "| Step | Type | Detail | Next |", "|---|---|---|---|"]
    for nid, n in flow.nodes.items():
        if n["type"] == "branch":
            nxt = f"yes -> `{n['yes']}`, no -> `{n['no']}`"
        else:
            nxt = f"`{n['next']}`" if n.get("next") else "end"
        detail = _label(nid, n)
        if n["type"] == "send":
            detail += f" (subject: `{n['subject']}`)"
            if n.get("vars"):
                detail += " vars: " + ", ".join(f"{k}={v}" for k, v in n["vars"].items())
        L.append(f"| `{nid}` | {n['type']} | {detail.replace('|', chr(92) + '|')} | {nxt} |")
    L += ["", "## Canvas", "", "```mermaid", "flowchart TD", f"  T([Trigger: {flow.trigger_event}]) --> {flow.start}"]
    for nid, n in flow.nodes.items():
        text = _label(nid, n).replace('"', "'").replace("`", "")
        shape = f'{{"{text}"}}' if n["type"] == "branch" else f'["{text}"]'
        L.append(f"  {nid}{shape}")
        if n["type"] == "branch":
            L += [f"  {nid} -->|yes| {n['yes']}", f"  {nid} -->|no| {n['no']}"]
        elif n.get("next"):
            L.append(f"  {nid} --> {n['next']}")
    L += ["```", "", "## Delivery rules applied to every send (global policy)", "",
          f"- Frequency caps across all flows: {caps}. A capped send is skipped, and the flow continues.",
          f"- Quiet hours: no sends between {policy.quiet_start}:00 and {policy.quiet_end}:00 customer-local time; "
          "the send is deferred to the end of the window and re-checked then.",
          "- Suppressed always: unsubscribed, hard-bounced, no marketing consent.",
          f"- Sunset: tiers {', '.join(policy.sunset_tiers)} are skipped unless the flow allows them.",
          "- Exit events are checked before every step, including a send that was deferred.", "", MAPPING]
    return "\n".join(L)


def load_raw_flows(directory: Path = FLOW_DIR):
    return [parse_flow(json.loads(p.read_text())) for p in sorted(directory.glob("*.json"))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="write docs/flows/*.md")
    a = ap.parse_args()
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    for f in load_raw_flows():
        text = render_spec(f)
        if a.write:
            (DOC_DIR / f"{f.id}.md").write_text(text)
        else:
            print(text)


if __name__ == "__main__":
    main()
