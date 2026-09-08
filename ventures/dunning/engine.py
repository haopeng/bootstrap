"""Sequence logic and reply triage.  No I/O, no LLM."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Optional

# (step, days relative to due date, tone)
SEQUENCE = [
    ("heads_up", -3, "friendly"),
    ("gentle", 1, "friendly"),
    ("firm", 7, "direct"),
    ("final", 14, "formal"),
]
HANDOFF_DAY = 30  # after this, a human decides (payment plan, pause, write-off, or a licensed agency)

BUSINESS_START, BUSINESS_END = time(9, 0), time(17, 0)


@dataclass
class Invoice:
    id: str
    customer: str
    email: str
    amount: float
    due: date
    currency: str = "USD"
    late_fee_allowed: bool = False    # only True if the signed terms say so
    late_fee_pct: float = 0.0
    pay_url: str = ""
    tz_offset_hours: int = 0          # customer's UTC offset for business-hours check
    status: str = "open"              # open | paid | disputed | paused | stopped | handoff
    sent_steps: list[str] = field(default_factory=list)
    promise_date: Optional[date] = None
    notes: list[str] = field(default_factory=list)


def in_business_hours(utc_now: datetime, tz_offset_hours: int) -> bool:
    local = utc_now.replace(tzinfo=None) + __import__("datetime").timedelta(hours=tz_offset_hours)
    return local.weekday() < 5 and BUSINESS_START <= local.time() < BUSINESS_END


def next_step(inv: Invoice, today: date) -> Optional[tuple[str, str]]:
    """Which step (if any) is due today for this invoice."""
    if inv.status != "open":
        return None
    if inv.promise_date and today <= inv.promise_date:
        return None  # customer promised a date; wait for it
    days = (today - inv.due).days
    if days >= HANDOFF_DAY:
        return ("handoff", "human")
    due_now = [(step, tone) for step, offset, tone in SEQUENCE if days >= offset and step not in inv.sent_steps]
    if not due_now:
        return None
    # If several steps are due (invoice onboarded already overdue), send only the
    # most severe one and record the earlier ones as skipped rather than sending a stale "heads-up".
    for step, _ in due_now[:-1]:
        inv.sent_steps.append(step)
        inv.notes.append(f"skipped {step}: onboarded {days} days past due")
    return due_now[-1]


# --- reply triage -----------------------------------------------------------
PAID = ("paid", "sent the payment", "wired", "check is in the mail", "just paid", "payment went out", "already paid")
DISPUTE = ("dispute", "incorrect", "wrong amount", "never received", "not what we agreed", "didn't order", "overcharg")
STOP = ("stop", "unsubscribe", "do not contact", "don't contact", "cease", "remove me", "harass")
PROMISE = ("will pay", "next week", "by friday", "end of month", "on the", "pay you on", "can pay", "schedule")


def triage(text: str) -> dict:
    t = text.lower()
    if any(w in t for w in STOP):
        return {"intent": "stop", "action": "Stop all automated contact; human reviews account."}
    if any(w in t for w in DISPUTE):
        return {"intent": "dispute", "action": "Pause sequence; human reviews the dispute within 1 business day."}
    if any(w in t for w in PAID):
        return {"intent": "paid_claim", "action": "Pause 5 business days; verify against bank/Stripe; thank them if confirmed."}
    if any(w in t for w in PROMISE):
        return {"intent": "promise", "action": "Record promised date; resume sequence the day after if unpaid."}
    return {"intent": "other", "action": "Human reads and replies."}


def apply_triage(inv: Invoice, intent: str, today: date, promise_date: Optional[date] = None) -> Invoice:
    if intent == "stop":
        inv.status = "stopped"
    elif intent == "dispute":
        inv.status = "disputed"
    elif intent == "paid_claim":
        inv.status = "paused"
        inv.promise_date = promise_date or date.fromordinal(today.toordinal() + 7)
    elif intent == "promise":
        inv.promise_date = promise_date or date.fromordinal(today.toordinal() + 7)
    return inv


def late_fee(inv: Invoice, today: date) -> float:
    if not inv.late_fee_allowed or today <= inv.due:
        return 0.0
    return round(inv.amount * inv.late_fee_pct / 100, 2)
