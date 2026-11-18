from datetime import timedelta

from lifecycle.engine import Policy, in_quiet_hours, next_send_window, run_customer
from lifecycle.flows import load_flows
from tests.helpers import CART, ENGAGED, T0, cust, ev

FLOWS = load_flows()


def run(c, flow_ids=None, policy=None, **kw):
    flows = {k: v for k, v in FLOWS.items() if not flow_ids or k in flow_ids}
    return run_customer(c, flows, policy, **kw)


def sent(recs):
    return [(r.node_id, r.ts) for r in recs if r.outcome == "sent"]


def test_quiet_hour_math():
    p = Policy()
    assert in_quiet_hours(T0.replace(hour=22), 0, p) and in_quiet_hours(T0.replace(hour=3), 0, p)
    assert not in_quiet_hours(T0.replace(hour=12), 0, p)
    # 22:00 UTC for a UTC-8 customer is 14:00 local: fine
    assert not in_quiet_hours(T0.replace(hour=22), -8, p)
    assert next_send_window(T0.replace(hour=22), 0, p) == (T0 + timedelta(days=1)).replace(hour=8)
    assert next_send_window(T0.replace(hour=3), 0, p) == T0.replace(hour=8)


def test_welcome_buyer_stops_after_first_email():
    c = cust(ENGAGED + [ev("signup", 0), ev("placed_order", 10)])
    recs, enr = run(c, ["welcome"])
    assert [r.template for r in recs] == ["welcome_1"]
    assert enr[0].outcome == "completed"


def test_welcome_nonbuyer_gets_three_and_branches_on_engagement():
    c = cust([ev("signup", 0)])  # new tier, not highly engaged -> incentive
    recs, _ = run(c, ["welcome"])
    assert [r.template for r in recs] == ["welcome_1", "welcome_2_incentive", "welcome_3_last_call"]
    assert recs[1].ts - recs[0].ts == timedelta(hours=48)
    assert recs[2].ts - recs[1].ts == timedelta(hours=72)
    assert recs[1].subject == "10% off your first order"
    c2 = cust([ev("signup", 0), ev("email_click", 1)])  # highly engaged -> story
    recs2, _ = run(c2, ["welcome"])
    assert recs2[1].template == "welcome_2_story"


def test_cart_exits_on_purchase_before_reminder():
    c = cust(ENGAGED + [ev("added_to_cart", 0, **CART), ev("placed_order", 0.5, value=62)])
    recs, enr = run(c, ["abandoned_cart"])
    assert recs == [] and enr[0].outcome == "exited:placed_order"


def test_cart_second_email_depends_on_segment():
    base = ENGAGED + [ev("added_to_cart", 0, **CART)]
    r1, _ = run(cust(base, attrs={"rfm_segment": "champions"}), ["abandoned_cart"])
    r2, _ = run(cust(base, attrs={"rfm_segment": "hibernating"}), ["abandoned_cart"])
    assert [r.template for r in r1] == ["cart_reminder_1", "cart_reminder_2"]
    assert [r.template for r in r2] == ["cart_reminder_1", "cart_reminder_2_incentive"]
    assert r2[1].subject == "5% off what is in your cart"


def test_cart_trigger_filter_small_cart_skips_and_reentry_window():
    small = ENGAGED + [ev("added_to_cart", 0, items=[], total=10)]
    assert run(cust(small), ["abandoned_cart"])[1] == []
    twice = ENGAGED + [ev("added_to_cart", 0, **CART), ev("added_to_cart", 24, **CART)]
    assert len(run(cust(twice), ["abandoned_cart"])[1]) == 1  # second is inside 72h
    later = ENGAGED + [ev("added_to_cart", 0, **CART), ev("added_to_cart", 80, **CART)]
    assert len(run(cust(later), ["abandoned_cart"])[1]) == 2


def test_quiet_hours_defer_not_drop_and_delays_restart_from_actual_send():
    # cart at 21:30 UTC -> reminder due 22:30 (quiet) -> deferred to 08:00 next day
    t = ev("added_to_cart", 9.5, **CART)  # T0 is 12:00, so +9.5h = 21:30
    c = cust(ENGAGED + [t], attrs={"rfm_segment": "champions"})
    recs, _ = run(c, ["abandoned_cart"])
    first = recs[0]
    assert first.ts == (T0 + timedelta(days=1)).replace(hour=8, minute=0)
    assert first.deferred_hours == 9.5
    assert recs[1].ts - first.ts == timedelta(hours=24)


def test_timezone_changes_quiet_hours():
    t = ev("added_to_cart", 9.5, **CART)  # 22:30 UTC due time
    sent_utc = run(cust(ENGAGED + [t], tz_offset=0), ["abandoned_cart"])[0][0]
    sent_la = run(cust(ENGAGED + [t], tz_offset=-8), ["abandoned_cart"])[0][0]  # 14:30 local
    assert sent_utc.deferred_hours > 0 and sent_la.deferred_hours == 0


def test_frequency_cap_counts_across_flows():
    # welcome_1 at 12:00, cart_1 at 13:00, then a third email within 24h must be capped (cap 2/24h)
    p = Policy(caps=((24, 2),))
    c2 = cust(ENGAGED + [ev("signup", 0), ev("added_to_cart", 0, **CART)])
    recs, _ = run(c2, ["welcome", "abandoned_cart"], p)
    day1 = [r for r in recs if r.ts < T0 + timedelta(hours=24)]
    assert sum(r.outcome == "sent" for r in day1) <= 2
    c3 = cust(ENGAGED + [ev("signup", 0), ev("added_to_cart", 0, **CART)])
    recs3, _ = run(c3, ["welcome", "abandoned_cart"], Policy(caps=((24, 1),)))
    assert any(r.reason == "frequency_cap_24h" for r in recs3)


def test_hard_suppressions():
    base = [ev("signup", 0)]
    r, _ = run(cust(base + [ev("unsubscribe", 1)]), ["welcome"])
    assert r[0].outcome == "sent"  # welcome_1 goes at t=0, before the unsubscribe
    assert all(x.reason == "unsubscribed_or_bounced" for x in r[1:]) and len(r) == 3
    r, _ = run(cust(base + [ev("hard_bounce", -1)]), ["welcome"])
    assert all(x.outcome == "suppressed" for x in r)
    r, _ = run(cust(base, marketing_consent=False), ["welcome"])
    assert {x.reason for x in r} == {"no_marketing_consent"}


def test_sunset_dormant_skipped_but_winback_allowed():
    long_ago = [ev("signup", -24 * 400)]
    r, _ = run(cust(long_ago + [ev("added_to_cart", 0, **CART)]), ["abandoned_cart"])
    assert r[0].reason == "sunset_dormant"
    r, _ = run(cust(long_ago + [ev("placed_order", 0, value=50)]), ["winback"])
    assert [x.outcome for x in r] == ["sent", "sent"] and r[0].template == "winback_1_offer"


def test_winback_day45_then_final_and_cancelled_by_later_order():
    c = cust([ev("signup", -24 * 400), ev("placed_order", 0, value=50)])
    recs, _ = run(c, ["winback"])
    assert recs[0].ts - T0 >= timedelta(days=45)
    assert [r.template for r in recs] == ["winback_1_offer", "winback_2_final"]
    c = cust([ev("signup", -24 * 400), ev("placed_order", 0, value=50), ev("placed_order", 24 * 20, value=40)])
    recs, enr = run(c, ["winback"])
    assert sorted(e.outcome for e in enr) == ["completed", "exited:placed_order"]
    assert recs[0].ts - (T0 + timedelta(days=20)) >= timedelta(days=45)


def test_onboarding_first_order_only_and_click_branch():
    c = cust(ENGAGED + [ev("placed_order", 0, value=50), ev("placed_order", 24 * 30, value=50)])
    recs, enr = run(c, ["onboarding"])
    assert len(enr) == 1
    assert [r.template for r in recs] == ["onboarding_1_tips", "onboarding_2_help"]
    clicked = cust(ENGAGED + [ev("placed_order", 0, value=50), ev("email_click", 24 * 5)])
    assert run(clicked, ["onboarding"])[0][1].template == "onboarding_2_referral"


def test_no_lookahead_orders_after_a_step_dont_change_it():
    # The purchase happens after the welcome_2 branch point (48h) -> still gets email 2
    c = cust([ev("signup", 0), ev("placed_order", 60, value=10)])
    recs, _ = run(c, ["welcome"])
    assert [r.template for r in recs][:2] == ["welcome_1", "welcome_2_incentive"]
    assert len(recs) == 2  # branch at 120h sees the order and exits


def test_horizon_leaves_enrollments_in_progress_and_live_from_ignores_history():
    c = cust([ev("signup", 0)])
    recs, enr = run(c, ["welcome"], horizon=T0 + timedelta(hours=10))
    assert len(recs) == 1 and enr[0].outcome == "in_progress"
    recs, enr = run(cust([ev("signup", -24)]), ["welcome"], live_from=T0)
    assert recs == [] and enr == []
