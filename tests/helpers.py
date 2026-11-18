from datetime import datetime, timedelta

from lifecycle.models import Customer, Event

T0 = datetime(2026, 3, 2, 12, 0)  # a Monday, noon UTC


def cust(events, **kw):
    kw.setdefault("tz_offset", 0)
    c = Customer(id="t1", first_name="Pat", email="t1@example.com", **kw)
    c.events = list(events)
    return c


def ev(name, hours=0, **props):
    return Event(T0 + timedelta(hours=hours), name, props)


ENGAGED = [ev("email_click", -24 * 2), ev("email_open", -24 * 2)]  # keeps tier out of dormant
CART = {"items": [{"name": "Desk lamp", "price": 62.0, "qty": 1}], "total": 62.0}
