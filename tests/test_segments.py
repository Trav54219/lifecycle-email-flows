from datetime import timedelta

from lifecycle.segments import ENGAGEMENT_TIERS, engagement_tier, rfm_scores, rfm_segment
from tests.helpers import T0, cust, ev


def test_rfm_segment_covers_every_cell():
    names = {rfm_segment(r, f) for r in range(1, 6) for f in range(1, 6)}
    assert names == {"champions", "loyal", "promising", "needs_attention", "at_risk", "hibernating"}
    assert rfm_segment(5, 5) == "champions" and rfm_segment(1, 1) == "hibernating"
    assert rfm_segment(1, 5) == "at_risk"


def test_rfm_scores_rank_and_skip_nonbuyers():
    def buyer(i, days_ago, n, value):
        c = cust([ev("placed_order", -24 * days_ago - k, value=value) for k in range(n)])
        c.id = f"b{i}"
        return c

    people = [buyer(0, 2, 10, 100), buyer(1, 300, 1, 10), buyer(2, 100, 3, 50), buyer(3, 5, 8, 80), buyer(4, 200, 1, 20)]
    nb = cust([ev("signup", -100)])
    nb.id = "nb"
    s = rfm_scores(people + [nb], T0)
    assert "nb" not in s
    assert s["b0"].r > s["b1"].r and s["b0"].f > s["b1"].f and s["b0"].m > s["b1"].m
    assert s["b0"].segment == "champions"
    assert all(1 <= v.r <= 5 and 1 <= v.f <= 5 and 1 <= v.m <= 5 for v in s.values())


def test_engagement_tiers():
    assert engagement_tier(cust([ev("signup", -24 * 400), ev("email_click", -24 * 3)]), T0) == "highly_engaged"
    assert engagement_tier(cust([ev("signup", -24 * 400)] + [ev("email_open", -24 * d) for d in (1, 2, 3)]), T0) == "highly_engaged"
    assert engagement_tier(cust([ev("signup", -24 * 400), ev("email_open", -24 * 60)]), T0) == "engaged"
    assert engagement_tier(cust([ev("signup", -24 * 10)]), T0) == "new"
    assert engagement_tier(cust([ev("signup", -24 * 400), ev("email_open", -24 * 150)]), T0) == "lapsing"
    assert engagement_tier(cust([ev("signup", -24 * 400)]), T0) == "dormant"
    assert engagement_tier(cust([ev("signup", -24 * 400)]), T0) in ENGAGEMENT_TIERS


def test_engagement_ignores_future_events():
    c = cust([ev("signup", -24 * 400), ev("email_click", 24)])
    assert engagement_tier(c, T0) == "dormant"
    assert engagement_tier(c, T0 + timedelta(hours=25)) == "highly_engaged"
