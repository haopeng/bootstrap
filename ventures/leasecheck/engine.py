from __future__ import annotations

import re

RULES = [
    ("auto_renew", r"automatic(ally)?\s+renew|shall renew|auto-?renew", "medium", "Automatic renewal",
     "The lease renews (often for a full year) unless you give notice in time.", "Ask for month-to-month after the initial term, or a 30-day notice window."),
    ("late_fee", r"late (fee|charge)[^.]{0,100}(\$\s?\d+|\d+\s?%)", "medium", "Late fee",
     "Late fees are capped or must be 'reasonable' in many states; a percentage above ~5% or a daily fee is a red flag.", "Ask for a grace period of 5 days and a cap."),
    ("nonrefundable_deposit", r"non-?refundable[^.]{0,60}deposit", "high", "'Non-refundable deposit'",
     "Security deposits are refundable by law in most states; calling one non-refundable is often unenforceable.", "Ask it to be renamed a fee with a stated purpose, or removed."),
    ("entry_notice", r"(enter|entry|access)[^.]{0,80}(without notice|at any time|any reasonable time without)", "high", "Landlord entry without notice",
     "Most states require 24-48 hours notice except in emergencies.", "Require 24 hours written notice except emergencies."),
    ("waiver", r"waive[sd]?[^.]{0,80}(right|jury|notice|claim)", "high", "Waiver of rights",
     "Waiving jury trial, notice periods or statutory rights is frequently void but signals an aggressive landlord.", "Strike the waiver."),
    ("joint_several", r"jointly and severally", "medium", "Joint and several liability",
     "You can be held responsible for a roommate's unpaid rent or damage.", "Ask for individual leases or a written roommate agreement."),
    ("early_term", r"(early termination|break)[^.]{0,80}(fee|penalt|\d+ months?)", "medium", "Early termination penalty",
     "Check the amount; two months' rent is typical, more is aggressive. Landlords must usually mitigate by re-renting.", "Negotiate a 1-2 month buyout."),
    ("repairs_tenant", r"tenant[^.]{0,60}(responsible|liable)[^.]{0,60}(all repairs|any repairs|maintenance)", "high", "Tenant pays for all repairs",
     "Landlords are responsible for habitability; shifting all repairs to you is often unenforceable.", "Limit tenant responsibility to damage they cause."),
    ("pets", r"pet (fee|rent|deposit)", "info", "Pet charges", "Pet fees/rent are stated.", "Confirm which are refundable."),
    ("attorney_fees", r"attorney'?s? fees", "low", "Attorney's fees clause",
     "Check that it is mutual (either party who wins gets fees), not one-sided.", "Make it mutual."),
    ("rent_increase", r"(increase|adjust)[^.]{0,60}rent[^.]{0,60}(any time|at (its|their) discretion|without notice)", "high", "Rent increase at landlord's discretion",
     "Rent should be fixed for the term.", "Fix rent for the full term; require 60 days notice for renewal increases."),
]

STATE_NOTES = {
    "CA": ["Security deposit capped at 1 month's rent for most leases (AB 12, since July 2024)", "Deposit must be returned within 21 days with itemized deductions", "24-hour written notice required for entry"],
    "TX": ["Deposit must be returned within 30 days", "Late fee must be 'reasonable'; safe harbor is 12% (10% for 5+ units) of monthly rent, after a 2-day grace period", "No statutory entry-notice requirement: negotiate one into the lease"],
    "NY": ["Deposit capped at 1 month's rent; return within 14 days", "Late fee capped at $50 or 5% of rent, whichever is less, after 5 days", "Landlord must give 30-90 days notice of non-renewal or rent increase over 5%, depending on tenancy length"],
    "WA": ["Deposit requires a written checklist at move-in; return within 30 days", "60 days notice for rent increases", "2 days notice for entry (1 day to show the unit)"],
    "IL": ["Chicago RLTO: deposit interest, 45-day return, 2 days notice for entry", "Statewide: 30-day return if no deductions"],
    "FL": ["Deposit return within 15 days (30 if claiming deductions)", "12 hours notice for entry at reasonable times"],
}


ASKS = {'auto_renew': 'convert the lease to month-to-month after the initial term (or a 30-day notice window instead of 60)', 'late_fee': 'add a 5-day grace period and cap the late fee at a flat amount, removing the per-day charge', 'nonrefundable_deposit': "remove the 'non-refundable deposit' or restate it as a fee with a defined purpose", 'entry_notice': 'require 24 hours written notice before entry, except emergencies', 'waiver': 'remove the jury-trial / rights waiver clause', 'joint_several': 'let each tenant be responsible for their own share, or attach a roommate agreement', 'early_term': "reduce the early-termination fee to two months' rent", 'repairs_tenant': 'limit tenant repair responsibility to damage we cause, with the landlord handling appliances and HVAC', 'pets': 'confirm which pet charges are refundable', 'attorney_fees': "make the attorney's-fees clause mutual", 'rent_increase': 'fix the rent for the full term'}


def scan(text: str) -> list[dict]:
    out = []
    for rid, pat, sev, title, detail, action in RULES:
        m = re.search(pat, text, re.I)
        if m:
            out.append({"rule": rid, "severity": sev, "title": title, "detail": detail, "action": action,
                        "evidence": text[max(0, m.start() - 50): m.end() + 50].replace("\n", " ").strip()})
    return out


def key_terms(text: str) -> dict:
    rent = re.search(r"(monthly rent|rent)[^$]{0,40}\$\s?([\d,]+(\.\d{2})?)", text, re.I)
    dep = re.search(r"(security )?deposit[^$]{0,40}\$\s?([\d,]+(\.\d{2})?)", text, re.I)
    term = re.search(r"term of (\w+ )?\(?(\d+)\)? months", text, re.I)
    return {"monthly_rent": rent.group(2) if rent else "?", "deposit": dep.group(2) if dep else "?",
            "term_months": term.group(2) if term else "?"}


def negotiation_email(findings: list[dict], landlord: str = "there") -> str:
    asks = [ASKS.get(f.get("rule", ""), f["action"]) for f in findings if f["severity"] in ("high", "medium")][:4]
    if not asks:
        return ""
    body = "\n".join(f"{i + 1}. {a}" for i, a in enumerate(asks))
    return (f"Hi {landlord},\n\nThanks for sending the lease. I'm excited about the place. Before I sign, could we adjust a few clauses?\n\n"
            f"{body}\n\nHappy to sign as soon as we agree on these. Thank you!\n")
