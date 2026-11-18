"""Synthetic-customer simulator.

Customer behavior (carts, orders, opens, clicks, unsubscribes) is generated up front from a
seeded RNG and does NOT respond to emails. The report therefore measures what the engine
decides to send and suppress, not revenue lift.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from .engine import Policy, run_customer
from .flows import load_flows
from .models import Customer, Event
from .segments import rfm_scores

START = datetime(2026, 1, 1)  # synthetic calendar, naive UTC
WINDOW_DAYS = 120
END = START + timedelta(days=WINDOW_DAYS)
FIRST_NAMES = ["Alex", "Sam", "Jordan", "Taylor", "Casey", "Riley", "Morgan", "Jamie", "Avery", "Quinn", ""]
CATALOG = [("Canvas tote", 28.0), ("Insulated bottle", 34.0), ("Desk lamp", 62.0), ("Wool throw", 89.0),
           ("Ceramic mug", 14.0), ("Standing mat", 120.0), ("Notebook set", 18.0)]


def _cart_event(rng: random.Random, ts: datetime) -> Event:
    items = []
    for name, price in rng.sample(CATALOG, rng.choice([1, 1, 2, 3])):
        items.append({"name": name, "price": price, "qty": rng.choice([1, 1, 2])})
    total = round(sum(i["price"] * i["qty"] for i in items), 2)
    return Event(ts, "added_to_cart", {"items": items, "total": total})


def generate_customers(n: int, seed: int) -> list[Customer]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        existing = rng.random() < 0.4
        c = Customer(id=f"c{i:05d}", first_name=rng.choice(FIRST_NAMES), email=f"c{i:05d}@example.com",
                     tz_offset=rng.choice([-8, -6, -5, 0, 1, 5]), marketing_consent=rng.random() < 0.93)
        ev = c.events
        signup = START - timedelta(days=rng.uniform(30, 700)) if existing else \
            START + timedelta(days=rng.uniform(0, WINDOW_DAYS - 5))
        ev.append(Event(signup, "signup"))
        if existing:
            for _ in range(rng.choices([0, 1, 2, 3, 5, 8], [15, 30, 20, 15, 12, 8])[0]):
                lo = max(signup, START - timedelta(days=365))
                ts = lo + (START - lo) * rng.random()
                ev.append(Event(ts, "placed_order", {"value": round(rng.uniform(20, 180), 2)}))
        else:
            if rng.random() < 0.25:  # first order inside the window
                ts = signup + timedelta(days=rng.uniform(0, 20))
                if ts < END:
                    ev.append(Event(ts, "placed_order", {"value": round(rng.uniform(20, 150), 2)}))
        # window behavior
        cart_rate = rng.choices([0, 0.004, 0.02, 0.05], [40, 30, 20, 10])[0]
        repeat_rate = 0.004 if existing else 0.002
        d0 = max(signup, START)
        days = int((END - d0).total_seconds() // 86400)
        for d in range(max(days, 0)):
            day = d0 + timedelta(days=d, hours=rng.uniform(0, 24))
            if rng.random() < cart_rate:
                cart = _cart_event(rng, day)
                ev.append(cart)
                if rng.random() < 0.35:  # converts, independent of any email
                    ev.append(Event(day + timedelta(hours=rng.uniform(0.2, 96)), "placed_order",
                                    {"value": cart.props["total"]}))
            elif rng.random() < repeat_rate:
                ev.append(Event(day, "placed_order", {"value": round(rng.uniform(20, 180), 2)}))
        # opens/clicks: background rate, independent of sends
        propensity = rng.betavariate(1.2, 2.5)
        e0 = max(signup, START - timedelta(days=120))
        for d in range(int((END - e0).total_seconds() // 86400)):
            if rng.random() < propensity * 0.2:
                ts = e0 + timedelta(days=d, hours=rng.uniform(0, 24))
                ev.append(Event(ts, "email_open"))
                if rng.random() < 0.25:
                    ev.append(Event(ts + timedelta(minutes=2), "email_click"))
        if rng.random() < 0.04:
            ev.append(Event(START + timedelta(days=rng.uniform(0, WINDOW_DAYS)), "unsubscribe"))
        elif rng.random() < 0.01:
            ev.append(Event(START + timedelta(days=rng.uniform(0, WINDOW_DAYS)), "hard_bounce"))
        ev[:] = [e for e in ev if e.ts <= END]
        out.append(c)
    return out


def simulate(n: int = 2000, seed: int = 7, policy: Policy | None = None) -> dict:
    policy = policy or Policy()
    flows = load_flows()
    customers = generate_customers(n, seed)
    rfm = rfm_scores(customers, START)  # snapshot at the start of the window
    for c in customers:
        if c.id in rfm:
            c.attrs["rfm_segment"] = rfm[c.id].segment
    records, enrollments = [], []
    for c in customers:
        r, e = run_customer(c, flows, policy, horizon=END, live_from=START)
        records += r
        enrollments += e
    return summarize(customers, records, enrollments, rfm, n, seed)


def summarize(customers, records, enrollments, rfm, n, seed) -> dict:
    per_flow = {}
    for fid in sorted({e.flow_id for e in enrollments} | {r.flow_id for r in records}):
        rs = [r for r in records if r.flow_id == fid]
        es = [e for e in enrollments if e.flow_id == fid]
        per_flow[fid] = {
            "enrolled": len(es),
            "exited_on_event": sum(e.outcome.startswith("exited") for e in es),
            "completed": sum(e.outcome == "completed" for e in es),
            "in_progress_at_end": sum(e.outcome == "in_progress" for e in es),
            "sent": sum(r.outcome == "sent" for r in rs),
            "suppressed": dict(Counter(r.reason for r in rs if r.outcome == "suppressed")),
            "sent_after_quiet_hours_deferral": sum(r.outcome == "sent" and r.deferred_hours > 0 for r in rs),
        }
    sent = [r for r in records if r.outcome == "sent"]
    per_day = defaultdict(int)
    for r in sent:
        per_day[(r.customer_id, r.ts.date())] += 1
    return {
        "synthetic": True, "customers": n, "seed": seed,
        "window": f"{START.date()} to {END.date()}",
        "send_attempts": len(records), "sent": len(sent),
        "suppressed": len(records) - len(sent),
        "customers_emailed": len({r.customer_id for r in sent}),
        "max_sends_per_customer_per_day": max(per_day.values(), default=0),
        "sent_by_template": dict(sorted(Counter(r.template for r in sent).items())),
        "rfm_segments": dict(sorted(Counter(v.segment for v in rfm.values()).items())),
        "flows": per_flow,
    }


def format_report(rep: dict) -> str:
    L = [f"SYNTHETIC RUN  customers={rep['customers']} seed={rep['seed']} window={rep['window']}",
         f"send attempts {rep['send_attempts']}  sent {rep['sent']}  suppressed {rep['suppressed']}  "
         f"customers emailed {rep['customers_emailed']}  max sends/customer/day {rep['max_sends_per_customer_per_day']}", ""]
    for fid, f in rep["flows"].items():
        L.append(f"[{fid}] enrolled {f['enrolled']}  completed {f['completed']}  exited on event {f['exited_on_event']}  "
                 f"in progress at end {f['in_progress_at_end']}")
        L.append(f"    sent {f['sent']} (quiet-hours deferred {f['sent_after_quiet_hours_deferral']})  suppressed {f['suppressed'] or 0}")
    L += ["", "sent by template:"] + [f"    {k}: {v}" for k, v in rep["sent_by_template"].items()]
    L += ["", "RFM snapshot (purchasers): " + ", ".join(f"{k}={v}" for k, v in rep["rfm_segments"].items())]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Run synthetic customers through the lifecycle flows.")
    ap.add_argument("--customers", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rep = simulate(a.customers, a.seed)
    print(json.dumps(rep, indent=2) if a.json else format_report(rep))


if __name__ == "__main__":
    main()
