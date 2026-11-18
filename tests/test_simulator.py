from datetime import timedelta

from lifecycle.flows import load_flows
from lifecycle.simulator import END, START, format_report, generate_customers, simulate


def test_deterministic_for_seed():
    assert simulate(150, seed=3) == simulate(150, seed=3)
    assert simulate(150, seed=3) != simulate(150, seed=4)


def test_generated_events_inside_window_or_history():
    for c in generate_customers(100, 1):
        assert all(e.ts <= END for e in c.events)
        assert c.email.endswith("@example.com")


def test_report_invariants():
    rep = simulate(400, seed=11)
    assert rep["synthetic"] is True
    assert rep["sent"] + rep["suppressed"] == rep["send_attempts"]
    assert rep["max_sends_per_customer_per_day"] <= 2  # default 24h cap
    assert sum(rep["sent_by_template"].values()) == rep["sent"]
    assert sum(f["sent"] for f in rep["flows"].values()) == rep["sent"]
    assert set(rep["flows"]) == set(load_flows())
    assert "SYNTHETIC" in format_report(rep)


def test_no_send_in_quiet_hours_or_after_unsubscribe_and_cap_holds():
    from lifecycle.engine import Policy, in_quiet_hours, run_customer
    from lifecycle.segments import rfm_scores

    flows, p = load_flows(), Policy()
    custs = generate_customers(300, 5)
    rfm = rfm_scores(custs, START)
    for c in custs:
        if c.id in rfm:
            c.attrs["rfm_segment"] = rfm[c.id].segment
    sent_total = 0
    for c in custs:
        recs, _ = run_customer(c, flows, p, horizon=END, live_from=START)
        s = [r for r in recs if r.outcome == "sent"]
        sent_total += len(s)
        stop = [e.ts for e in c.events if e.name in ("unsubscribe", "hard_bounce")]
        for r in s:
            assert not in_quiet_hours(r.ts, c.tz_offset, p)
            assert not any(u <= r.ts for u in stop)
            assert c.marketing_consent
        for r in s:
            for hours, cap in p.caps:
                n = sum(1 for o in s if r.ts - timedelta(hours=hours) < o.ts <= r.ts)
                assert n <= cap
    assert sent_total > 0
