import pytest

from lifecycle.conditions import Context, describe, evaluate
from tests.helpers import T0, cust, ev


def ctx(c, hours=0, trig=0, props=None):
    from datetime import timedelta
    return Context(c, T0 + timedelta(hours=hours), T0 + timedelta(hours=trig), props or {})


def test_did_since_trigger_excludes_trigger_instant_and_future():
    c = cust([ev("placed_order", 0), ev("placed_order", 5), ev("placed_order", 50)])
    cond = {"did": {"event": "placed_order", "since": "trigger"}}
    assert evaluate(cond, ctx(c, hours=4)) is False  # trigger-instant order excluded, future hidden
    assert evaluate(cond, ctx(c, hours=6)) is True
    assert evaluate({"did": {"event": "placed_order", "since": "trigger"}}, ctx(c, hours=-1)) is False


def test_did_window():
    c = cust([ev("email_click", -30)])
    assert evaluate({"did": {"event": "email_click", "hours": 24}}, ctx(c)) is False
    assert evaluate({"did": {"event": "email_click", "hours": 48}}, ctx(c)) is True


def test_count_attr_trigger_prop_and_combinators():
    c = cust([ev("placed_order", -5), ev("placed_order", 0)], attrs={"rfm_segment": "loyal", "plan": 3})
    assert evaluate({"count": {"event": "placed_order", "op": "==", "value": 2}}, ctx(c))
    assert not evaluate({"count": {"event": "placed_order", "op": "==", "value": 2}}, ctx(c, hours=-1))
    assert evaluate({"attr": {"key": "plan", "op": ">=", "value": 3}}, ctx(c))
    assert not evaluate({"attr": {"key": "missing", "op": "==", "value": 1}}, ctx(c))
    assert evaluate({"trigger_prop": {"key": "total", "op": ">=", "value": 20}}, ctx(c, props={"total": 20}))
    assert evaluate({"segment": "loyal"}, ctx(c))
    assert evaluate({"all": [{"segment": "loyal"}, {"not": {"segment": "champions"}}]}, ctx(c))
    assert evaluate({"any": [{"segment": "champions"}, {"segment": "loyal"}]}, ctx(c))


def test_bad_condition_raises_and_describe():
    with pytest.raises(ValueError):
        evaluate({"bogus": 1}, ctx(cust([])))
    with pytest.raises(ValueError):
        evaluate({"a": 1, "b": 2}, ctx(cust([])))
    assert "OR" in describe({"any": [{"segment": "a"}, {"segment": "b"}]})
