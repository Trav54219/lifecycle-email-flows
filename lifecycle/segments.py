"""Segment definitions: RFM scoring and engagement tiers."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta

from .models import Customer


@dataclass(frozen=True)
class RFM:
    r: int
    f: int
    m: int
    segment: str


def purchase_stats(customer: Customer, now: datetime):
    orders = [e for e in customer.events if e.name == "placed_order" and e.ts <= now]
    if not orders:
        return None
    last = max(e.ts for e in orders)
    spend = sum(float(e.props.get("value", 0)) for e in orders)
    return (now - last).total_seconds() / 86400, len(orders), spend


def _score_higher_better(value: float, sorted_pop: list[float]) -> int:
    """1-5 by the share of the population strictly below `value` (ties share a score)."""
    below = bisect_left(sorted_pop, value)
    return min(5, 1 + int(5 * below / len(sorted_pop)))


def _score_lower_better(value: float, sorted_pop: list[float]) -> int:
    above = len(sorted_pop) - bisect_right(sorted_pop, value)
    return min(5, 1 + int(5 * above / len(sorted_pop)))


def rfm_segment(r: int, f: int) -> str:
    """Segment names from R and F scores. Covers every (r, f) in 1..5 x 1..5."""
    if r >= 4 and f >= 4:
        return "champions"
    if r >= 3 and f >= 3:
        return "loyal"
    if r >= 4:
        return "promising"
    if r == 3:
        return "needs_attention"
    if f >= 3:
        return "at_risk"
    return "hibernating"


def rfm_scores(customers: list[Customer], now: datetime) -> dict[str, RFM]:
    """Quintile RFM over purchasers only. Customers with no orders get no entry."""
    stats = {c.id: s for c in customers if (s := purchase_stats(c, now))}
    if not stats:
        return {}
    rec = sorted(s[0] for s in stats.values())
    freq = sorted(float(s[1]) for s in stats.values())
    mon = sorted(s[2] for s in stats.values())
    out = {}
    for cid, (recency, f_, m_) in stats.items():
        r = _score_lower_better(recency, rec)
        f = _score_higher_better(f_, freq)
        m = _score_higher_better(m_, mon)
        out[cid] = RFM(r, f, m, rfm_segment(r, f))
    return out


ENGAGEMENT_TIERS = ("highly_engaged", "engaged", "new", "lapsing", "dormant")


def engagement_tier(customer: Customer, now: datetime) -> str:
    """Tier from email opens/clicks. Evaluated at `now` using only events up to `now`."""

    def count(name: str, days: int) -> int:
        lo = now - timedelta(days=days)
        return sum(1 for e in customer.events if e.name == name and lo < e.ts <= now)

    if count("email_click", 30) >= 1 or count("email_open", 30) >= 3:
        return "highly_engaged"
    if count("email_open", 90) >= 1 or count("email_click", 90) >= 1:
        return "engaged"
    signups = [e.ts for e in customer.events if e.name == "signup" and e.ts <= now]
    if signups and now - min(signups) <= timedelta(days=30):
        return "new"
    if count("email_open", 180) >= 1 or count("email_click", 180) >= 1:
        return "lapsing"
    return "dormant"
