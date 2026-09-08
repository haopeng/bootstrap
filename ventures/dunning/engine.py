"""Sequence logic and reply triage.  No I/O, no LLM."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Optional

# Cadence per relationship profile: (step, days relative to due date, tone).
# The article's detail: long-time customers get a warmer, slower sequence;
# chronic late payers get urgency earlier and a phone call at the "firm" step.
SEQUENCES = {
    "warm": [("heads_up", -3, "friendly"), ("gentle", 3, "friendly"), ("firm", 10, "direct"), ("final", 18, "formal")],
    "standard": [("heads_up", -3, "friendly"), ("gentle", 1, "friendly"), ("firm", 7, "direct"), ("final", 14, "formal")],
    "urgent": [("heads_up", -3, "friendly"), ("gentle", 1, "direct"), ("firm", 4, "direct"), ("final", 10, "formal")],
}
SEQUENCE = SEQUENCES["standard"]
CALL_AT = {"warm": set(), "standard": {"final"}, "urgent": {"firm", "final"}}  # steps that also trigger a phone call
HANDOFF_DAY = 30  # after this, a human decides (payment plan, pause, write-off, or a licensed agency)

BUSINESS_START, BUSINESS_END = time(9, 0), time(17, 0)


@dataclass
class CustomerHistory:
    """What the accounting system knows about this customer."""
    invoices_paid: int = 0
    avg_days_to_pay: float = 0.0     # relative to due date; negative = early
    late_count: int = 0              # invoices paid 7+ days late
    years_as_customer: float = 0.0
    open_balance: float = 0.0

    def profile(self) -> str:
        if self.invoices_paid >= 6 and self.late_count <= max(1, self.invoices_paid // 5) and self.avg_days_to_pay <= 5:
            return "warm"
        if self.invoices_paid >= 2 and (self.late_count >= max(2, self.invoices_paid // 2) or self.avg_days_to_pay > 20):
            return "urgent"
        return "standard"


@dataclass
class Invoice:
    id: str
    customer: str
    email: str
    amount: float
    due: date
    currency: str = "USD"
    phone: str = ""                   # AP contact number (business line) for the call step
    history: CustomerHistory = field(default_factory=CustomerHistory)
    late_fee_allowed: bool = False    # only True if the signed terms say so
    late_fee_pct: float = 0.0
    pay_url: str = ""
    tz_offset_hours: int = 0          # customer's UTC offset for business-hours check
    status: str = "open"              # open | paid | disputed | paused | stopped | handoff
    sent_steps: list[str] = field(default_factory=list)
    promise_date: Optional[date] = None
    last_touch: Optional[date] = None
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
    seq = SEQUENCES[inv.history.profile()]
    due_now = [(step, tone) for step, offset, tone in seq if days >= offset and step not in inv.sent_steps]
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
    if any(w in t for w in PROMISE) or parse_promise(text, date.today()):
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


# --- natural-language promise dates ------------------------------------------
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_promise(text: str, today: date) -> Optional[date]:
    """'we'll pay next week' / 'by Friday' / 'end of month' / 'on the 15th' / '9/20' / 'in 3 days' -> date.
    Deterministic so a call transcript updates the invoice even when the model is unavailable."""
    import re
    from datetime import timedelta

    t = text.lower()
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", t)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", t)
    if m:
        y = int(m[3]) if m[3] else today.year
        y = y + 2000 if y < 100 else y
        try:
            d = date(y, int(m[1]), int(m[2]))
            return d if d >= today else d.replace(year=y + 1)
        except ValueError:
            pass
    m = re.search(r"\b(" + "|".join(_MONTHS) + r")[a-z]*\.? (\d{1,2})(?:st|nd|rd|th)?\b", t)
    if m:
        d = date(today.year, _MONTHS[m[1]], int(m[2]))
        return d if d >= today else d.replace(year=today.year + 1)
    if "tomorrow" in t:
        return today + timedelta(days=1)
    if "today" in t or "this afternoon" in t or "right now" in t:
        return today
    m = re.search(r"in (\d+) (day|week)s?", t)
    if m:
        return today + timedelta(days=int(m[1]) * (7 if m[2] == "week" else 1))
    if "end of (the )?month" in t or re.search(r"end of (the )?month", t):
        nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        return nxt - timedelta(days=1)
    if "next month" in t:
        nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        return nxt + timedelta(days=4)
    m = re.search(r"(?:on |by |this |next )?(" + "|".join(_WEEKDAYS) + r")\b", t)
    if m:
        target = _WEEKDAYS.index(m[1])
        ahead = (target - today.weekday()) % 7 or 7
        if "next " + m[1] in t and ahead <= 7 and today.weekday() >= target:
            pass
        elif "next " + m[1] in t:
            ahead += 7
        return today + timedelta(days=ahead)
    if "next week" in t:
        return today + timedelta(days=(7 - today.weekday()) + 4)  # next Friday: businesses pay on pay runs
    if "this week" in t:
        return today + timedelta(days=max(4 - today.weekday(), 0))
    m = re.search(r"\b(?:on |by )?the (\d{1,2})(?:st|nd|rd|th)\b", t)
    if m:
        day = int(m[1])
        try:
            d = today.replace(day=day)
        except ValueError:
            return None
        if d < today:
            nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
            d = nxt.replace(day=min(day, 28))
        return d
    return None


def late_fee(inv: Invoice, today: date) -> float:
    if not inv.late_fee_allowed or today <= inv.due:
        return 0.0
    return round(inv.amount * inv.late_fee_pct / 100, 2)
