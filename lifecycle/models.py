from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Event:
    ts: datetime
    name: str
    props: dict[str, Any] = field(default_factory=dict)


@dataclass
class Customer:
    id: str
    first_name: str
    email: str
    tz_offset: int = 0  # whole hours from UTC
    marketing_consent: bool = True
    events: list[Event] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)  # e.g. rfm_segment snapshot


@dataclass
class Enrollment:
    flow_id: str
    customer_id: str
    ts: datetime
    trigger_props: dict[str, Any]
    outcome: str = "in_progress"  # completed | exited:<event> | in_progress
    exit_ts: datetime | None = None


@dataclass
class Record:
    """One send attempt: either sent or suppressed (with a reason)."""

    customer_id: str
    flow_id: str
    node_id: str
    template: str
    ts: datetime
    outcome: str  # "sent" | "suppressed"
    reason: str = ""
    subject: str = ""
    deferred_hours: float = 0.0  # quiet-hours deferral applied before this attempt
