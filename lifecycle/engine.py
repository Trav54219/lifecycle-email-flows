"""Flow engine: enrolls a customer on trigger events and walks the flow graph in time order.

All flows for one customer share one event queue, so frequency caps count sends across flows.
Send pipeline (in order): hard suppressions -> quiet-hours deferral -> frequency caps -> send.
"""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass
from datetime import datetime, timedelta

from .conditions import Context, evaluate
from .flows import Flow
from .models import Customer, Enrollment, Record
from .segments import engagement_tier
from .templates import render


@dataclass
class Policy:
    caps: tuple[tuple[int, int], ...] = ((24, 2), (168, 4))  # (window_hours, max_sends)
    quiet_start: int = 21  # local hour, inclusive
    quiet_end: int = 8  # local hour, exclusive
    sunset_tiers: tuple[str, ...] = ("dormant",)


def in_quiet_hours(ts: datetime, tz_offset: int, p: Policy) -> bool:
    h = (ts + timedelta(hours=tz_offset)).hour
    if p.quiet_start > p.quiet_end:
        return h >= p.quiet_start or h < p.quiet_end
    return p.quiet_start <= h < p.quiet_end


def next_send_window(ts: datetime, tz_offset: int, p: Policy) -> datetime:
    """Earliest time >= ts outside quiet hours (the quiet_end hour in the customer's local time)."""
    local = ts + timedelta(hours=tz_offset)
    target = local.replace(hour=p.quiet_end, minute=0, second=0, microsecond=0)
    if target < local:
        target += timedelta(days=1)
    return target - timedelta(hours=tz_offset)


def _template_scope(customer: Customer, now: datetime, node: dict) -> dict:
    carts = [e for e in customer.events if e.name == "added_to_cart" and e.ts <= now]
    orders = [e for e in customer.events if e.name == "placed_order" and e.ts <= now]
    cart = carts[-1].props if carts else {}
    return {
        "brand": {"name": "Northwind Goods", "address": "100 Example Way, Sampleton (synthetic)"},
        "customer": {"first_name": customer.first_name, "email": customer.email},
        "cart": {"items": cart.get("items", []), "total": cart.get("total", 0)},
        "order": {"count": len(orders), "last_value": orders[-1].props.get("value", 0) if orders else 0},
        "offer": node.get("vars", {}),
        "unsubscribe_url": f"https://example.com/unsubscribe?c={customer.id}",
    }


def run_customer(customer: Customer, flows: dict[str, Flow], policy: Policy | None = None,
                 horizon: datetime | None = None,
                 live_from: datetime | None = None) -> tuple[list[Record], list[Enrollment]]:
    """Run every flow for one customer. Steps scheduled after `horizon` are left in_progress.
    Trigger events before `live_from` are ignored (the flow was not live yet)."""
    policy = policy or Policy()
    events = sorted(customer.events, key=lambda e: e.ts)
    customer.events = events
    heap: list = []
    seq = itertools.count()
    enrollments: list[Enrollment] = []
    records: list[Record] = []
    ledger: list[datetime] = []

    for flow in flows.values():
        last = None
        for ev in events:
            if ev.name != flow.trigger_event or (live_from and ev.ts < live_from):
                continue
            if flow.trigger_filter and not evaluate(flow.trigger_filter, Context(customer, ev.ts, ev.ts, ev.props)):
                continue
            if last is not None:
                if flow.reentry_hours is None or ev.ts - last < timedelta(hours=flow.reentry_hours):
                    continue
            last = ev.ts
            enr = Enrollment(flow.id, customer.id, ev.ts, dict(ev.props))
            enrollments.append(enr)
            heapq.heappush(heap, (ev.ts, next(seq), enr, flow.start, 0.0))

    unsub = [e.ts for e in events if e.name in ("unsubscribe", "hard_bounce")]

    def push(t, enr, node_id, deferred=0.0):
        heapq.heappush(heap, (t, next(seq), enr, node_id, deferred))

    while heap:
        t, _, enr, node_id, deferred = heapq.heappop(heap)
        flow = flows[enr.flow_id]
        if horizon is not None and t > horizon:
            continue  # outcome stays in_progress
        hit = next((e for e in events if e.name in flow.exit_events and enr.ts < e.ts <= t), None)
        if hit:
            enr.outcome, enr.exit_ts = f"exited:{hit.name}", t
            continue
        node = flow.nodes[node_id]
        kind = node["type"]
        ctx = Context(customer, t, enr.ts, enr.trigger_props)
        if kind == "delay":
            push(t + timedelta(hours=node["hours"]), enr, node["next"])
        elif kind == "branch":
            push(t, enr, node["yes"] if evaluate(node["condition"], ctx) else node["no"])
        elif kind == "exit":
            enr.outcome, enr.exit_ts = "completed", t
        elif kind == "send":
            reason = _suppression(customer, flow, t, unsub, policy)
            if reason is None and not deferred and in_quiet_hours(t, customer.tz_offset, policy):
                t2 = next_send_window(t, customer.tz_offset, policy)
                push(t2, enr, node_id, (t2 - t).total_seconds() / 3600)
                continue
            if reason is None:
                for hours, cap in policy.caps:
                    lo = t - timedelta(hours=hours)
                    if sum(1 for s in ledger if lo < s <= t) >= cap:
                        reason = f"frequency_cap_{hours}h"
                        break
            scope = _template_scope(customer, t, node)
            subject = render(node.get("subject", ""), scope)
            rec = Record(customer.id, flow.id, node_id, node["template"], t,
                         "suppressed" if reason else "sent", reason or "", subject, deferred)
            records.append(rec)
            if not reason:
                ledger.append(t)
            if node.get("next"):
                push(t, enr, node["next"])
            else:
                enr.outcome, enr.exit_ts = "completed", t
    return records, enrollments


def _suppression(customer: Customer, flow: Flow, t: datetime, unsub: list[datetime],
                 policy: Policy) -> str | None:
    if any(u <= t for u in unsub):
        return "unsubscribed_or_bounced"
    if not customer.marketing_consent:
        return "no_marketing_consent"
    if not flow.allow_dormant and engagement_tier(customer, t) in policy.sunset_tiers:
        return "sunset_dormant"
    return None
