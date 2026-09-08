"""Lead scoring and deal math.  Pure functions, no I/O."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from .records import Record

# How strongly each public signal predicts a motivated seller (0-1).
SIGNAL_WEIGHT = {
    "probate": 0.9, "pre_foreclosure": 0.85, "tax_lien": 0.8, "divorce": 0.6,
    "code_violation": 0.5, "vacant": 0.45,
}


def _same_addr(a: str, b: str) -> bool:
    norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())
    na, nb = norm(a), norm(b)
    return bool(na) and bool(nb) and (na.startswith(nb) or nb.startswith(na))


def build_leads(records: list[Record], today: date | None = None) -> list[dict]:
    """Group records by parcel, stack signals, compute a 0-100 motivation score."""
    today = today or date.today()
    by_parcel: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        by_parcel[r.parcel or r.address].append(r)
    leads = []
    for key, rs in by_parcel.items():
        base = rs[0]
        signals = sorted({r.signal for r in rs}, key=lambda s: -SIGNAL_WEIGHT[s])
        strongest = SIGNAL_WEIGHT[signals[0]]
        stacked = 1 - (1 - strongest) * (0.6 ** (len(signals) - 1))  # each extra signal closes 40% of the gap
        absentee = bool(base.owner_mailing) and not _same_addr(base.address, base.owner_mailing)
        newest = max(r.filed for r in rs)
        age_days = (today - newest).days
        recency = 1.0 if age_days <= 30 else 0.8 if age_days <= 90 else 0.55 if age_days <= 365 else 0.3
        arrears = sum(r.amount for r in rs)
        equity_ratio = 1 - (arrears / base.assessed_value if base.assessed_value else 0)
        score = 100 * stacked * recency * (1.1 if absentee else 1.0) * (1.0 if equity_ratio > 0.4 else 0.7)
        leads.append({
            "key": key, "address": base.address, "city": base.city, "state": base.state, "zip": base.zip,
            "owner": base.owner, "owner_mailing": base.owner_mailing or base.address, "phone": base.phone,
            "signals": signals, "absentee": absentee, "newest_filing": newest.isoformat(), "age_days": age_days,
            "assessed_value": base.assessed_value, "arrears": arrears, "equity_ratio": round(equity_ratio, 2),
            "score": round(min(score, 100), 1), "notes": "; ".join(n for n in (r.notes for r in rs) if n),
        })
    leads.sort(key=lambda l: -l["score"])
    return leads


def deal_math(lead: dict, arv_multiplier: float = 1.15, repair_per_sqft: float = 25.0, sqft: int = 1500,
              assignment_fee: float = 10000.0) -> dict:
    """Wholesaler's 70% rule.  ARV is estimated from assessed value until comps are pulled."""
    arv = lead["assessed_value"] * arv_multiplier
    repairs = repair_per_sqft * sqft
    mao = arv * 0.70 - repairs - assignment_fee  # max allowable offer to the seller
    return {
        "arv_estimate": round(arv), "repairs_estimate": round(repairs), "assignment_fee": assignment_fee,
        "max_offer": round(max(mao, 0)), "investor_price": round(max(mao, 0) + assignment_fee),
        "investor_gross_margin": round(arv - (max(mao, 0) + assignment_fee) - repairs),
        "note": "ARV = assessed x 1.15 placeholder; replace with 3 sold comps within 0.5 mi / 6 months before offering.",
    }
