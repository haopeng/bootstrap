"""No monthly fee; 10% of what the sequence actually recovers.

Attribution rule (the part customers will argue about, so it is explicit):
a payment counts as recovered if (a) at least one reminder or call went out on
that invoice, (b) the invoice was past due when the first reminder went out,
and (c) payment arrived within ATTRIBUTION_DAYS of the last touch.  Pre-due
"heads-up" emails alone never count: the customer was going to pay anyway."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .engine import Invoice

FEE_PCT = 10.0
ATTRIBUTION_DAYS = 21
CHASING_STEPS = {"gentle", "firm", "final"}


@dataclass
class Recovery:
    invoice_id: str
    customer: str
    amount: float
    paid_on: date
    attributed: bool
    reason: str
    fee: float


@dataclass
class RecoveryLedger:
    items: list[Recovery] = field(default_factory=list)

    def record(self, inv: Invoice, amount: float, paid_on: date, last_touch: date | None) -> Recovery:
        chased = [s for s in inv.sent_steps if s in CHASING_STEPS and not any(n.startswith(f"skipped {s}") for n in inv.notes)]
        if not chased:
            attributed, reason = False, "no past-due reminder was sent"
        elif last_touch is None or (paid_on - last_touch).days > ATTRIBUTION_DAYS:
            attributed, reason = False, f"paid more than {ATTRIBUTION_DAYS} days after last touch"
        else:
            attributed, reason = True, f"paid {(paid_on - last_touch).days} days after '{chased[-1]}'"
        r = Recovery(inv.id, inv.customer, round(amount, 2), paid_on, attributed, reason,
                     round(amount * FEE_PCT / 100, 2) if attributed else 0.0)
        self.items.append(r)
        inv.status = "paid" if amount >= inv.amount - 0.005 else inv.status
        return r

    def statement(self, period: str) -> dict:
        rec = [r for r in self.items if r.attributed]
        return {"period": period, "recovered": round(sum(r.amount for r in rec), 2), "fee_pct": FEE_PCT,
                "fee_due": round(sum(r.fee for r in rec), 2), "invoices": len(rec),
                "not_attributed": [(r.invoice_id, r.reason) for r in self.items if not r.attributed]}
