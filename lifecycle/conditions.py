"""A small condition DSL used by flow branches, trigger filters and exits.

Shapes (JSON-friendly):
  {"did": {"event": "placed_order", "since": "trigger"}}      events after enrollment
  {"did": {"event": "email_click", "hours": 24}}               events in the last N hours
  {"count": {"event": "placed_order", "op": "==", "value": 1}}  events up to now
  {"segment": "champions"}                                      RFM snapshot or live engagement tier
  {"attr": {"key": "plan", "op": "==", "value": "x"}}
  {"trigger_prop": {"key": "total", "op": ">=", "value": 20}}   props of the enrolling event
  {"all": [...]}  {"any": [...]}  {"not": {...}}
Only events with ts <= now are ever visible (no look-ahead).
"""
from __future__ import annotations

import operator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .models import Customer
from .segments import engagement_tier

OPS = {"==": operator.eq, "!=": operator.ne, ">": operator.gt, ">=": operator.ge,
       "<": operator.lt, "<=": operator.le}


@dataclass
class Context:
    customer: Customer
    now: datetime
    trigger_ts: datetime
    trigger_props: dict[str, Any] = field(default_factory=dict)


def evaluate(cond: dict, ctx: Context) -> bool:
    if len(cond) != 1:
        raise ValueError(f"condition must have exactly one key: {cond}")
    (kind, arg), = cond.items()
    if kind == "all":
        return all(evaluate(c, ctx) for c in arg)
    if kind == "any":
        return any(evaluate(c, ctx) for c in arg)
    if kind == "not":
        return not evaluate(arg, ctx)
    if kind == "did":
        lo = ctx.trigger_ts if arg.get("since") == "trigger" else ctx.now - timedelta(hours=arg["hours"])
        return any(e.name == arg["event"] and lo < e.ts <= ctx.now for e in ctx.customer.events)
    if kind == "count":
        n = sum(1 for e in ctx.customer.events if e.name == arg["event"] and e.ts <= ctx.now)
        return OPS[arg["op"]](n, arg["value"])
    if kind == "segment":
        return arg == ctx.customer.attrs.get("rfm_segment") or arg == engagement_tier(ctx.customer, ctx.now)
    if kind == "attr":
        return arg["key"] in ctx.customer.attrs and OPS[arg["op"]](ctx.customer.attrs[arg["key"]], arg["value"])
    if kind == "trigger_prop":
        return arg["key"] in ctx.trigger_props and OPS[arg["op"]](ctx.trigger_props[arg["key"]], arg["value"])
    raise ValueError(f"unknown condition type: {kind}")


def describe(cond: dict) -> str:
    (kind, arg), = cond.items()
    if kind in ("all", "any"):
        return "(" + (" OR " if kind == "any" else " AND ").join(describe(c) for c in arg) + ")"
    if kind == "not":
        return "NOT " + describe(arg)
    if kind == "did":
        when = "since entering the flow" if arg.get("since") == "trigger" else f"in the last {arg['hours']}h"
        return f"customer did `{arg['event']}` {when}"
    if kind == "count":
        return f"count of `{arg['event']}` {arg['op']} {arg['value']}"
    if kind == "segment":
        return f"customer is in segment `{arg}`"
    if kind == "attr":
        return f"attribute `{arg['key']}` {arg['op']} {arg['value']}"
    if kind == "trigger_prop":
        return f"trigger event property `{arg['key']}` {arg['op']} {arg['value']}"
    raise ValueError(kind)
