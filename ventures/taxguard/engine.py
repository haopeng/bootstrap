"""Deterministic rules.  These are the checks a bookkeeper does by eye; the LLM
layer adds nuance on top but this layer alone catches the expensive mistakes."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from .ingest import Doc

# (rule id, regex, severity, title, detail, action)
CLAUSE_RULES = [
    ("auto_renew", r"automatic(ally)?\s+renew|auto-?renew|shall renew", "high",
     "Automatic renewal clause",
     "The term renews unless you cancel in advance. Missed windows are the #1 source of unwanted vendor spend.",
     "Add the cancellation deadline to your calendar; negotiate a 30-day, not 90-day, notice window."),
    ("unlimited_indemnity", r"indemnif(y|ies|ication)[^.]{0,200}(any and all|all claims|without limit)", "high",
     "Broad / uncapped indemnification",
     "You may be on the hook for the other party's losses with no cap.",
     "Cap indemnity at fees paid in the prior 12 months and exclude consequential damages."),
    ("late_fee", r"late (fee|charge|payment)[^.]{0,120}(\d+(\.\d+)?\s*%|\$\s?\d+)", "medium",
     "Late-payment penalty",
     "A late fee or interest rate is specified; verify it does not exceed your state's usury cap.",
     "Confirm the rate and net-terms match the PO; set an internal pay-by date 5 days early."),
    ("net_terms", r"\bnet\s?(15|30|45|60|90)\b", "info",
     "Payment terms detected", "Payment terms are stated in the document.", "Record terms in AP system."),
    ("non_compete", r"non-?compet(e|ition)", "medium",
     "Non-compete", "Restricts who you can work with; enforceability varies by state and the FTC has challenged them.",
     "Narrow scope to named competitors and a 6-12 month window."),
    ("assignment", r"may (not )?assign[^.]{0,120}(without|prior written consent)", "low",
     "Assignment restriction", "You may need consent to transfer the contract if you sell the business.",
     "Carve out assignment to an affiliate or acquirer."),
    ("governing_law", r"governed by the laws of (the state of )?([A-Z][a-z]+( [A-Z][a-z]+)?)", "info",
     "Governing law", "Disputes are governed by another jurisdiction's law.", "Prefer your home state; at least require venue nearby."),
    ("unilateral_change", r"(reserve|reserves) the right to (change|modify|amend)[^.]{0,80}(at any time|without notice)", "high",
     "Unilateral price/term changes", "The vendor can change price or terms without your consent.",
     "Require 30 days written notice and a right to terminate without penalty."),
    ("liquidated_damages", r"liquidated damages", "medium",
     "Liquidated damages", "A fixed penalty applies on breach; make sure it is proportionate.",
     "Tie the amount to actual, documented loss."),
    ("perpetual_license", r"perpetual[^.]{0,60}(license|licence|right)", "low",
     "Perpetual license grant", "You may be granting rights that outlive the contract.",
     "Limit license to the term of the agreement."),
    ("confidentiality_term", r"confidential[^.]{0,120}(\d+)\s*(years?|months?)", "info",
     "Confidentiality term", "Confidentiality obligations have a stated duration.", "Record obligation end date."),
    ("missing_termination", None, "medium",
     "No termination-for-convenience clause found", "You may not be able to exit without breaching.",
     "Add: 'Either party may terminate on 30 days written notice.'"),
]

# US federal information-return thresholds (tax year 2026 figures).
# Note: the 2025 reconciliation act raised the 1099-NEC/MISC threshold from
# $600 to $2,000 starting with payments made in 2026, indexed after 2027.
NEC_THRESHOLD = 2000.0
K_THRESHOLD = 20000.0  # 1099-K reverted to $20,000 / 200 transactions for 2025+.

MONEY = re.compile(r"\$\s?([0-9]{1,3}(,[0-9]{3})*(\.[0-9]{2})?|[0-9]+(\.[0-9]{2})?)")
VENDOR = re.compile(r"(?:from|vendor|payee|bill to|billed by|contractor)[:\s]+([A-Z][A-Za-z&.,' -]{2,60})", re.I)
TOTAL = re.compile(r"(?:total|amount due|balance due|grand total)[:\s]*\$?\s?([0-9][0-9,]*(\.[0-9]{2})?)", re.I)
ENTITY_WORDS = re.compile(r"\b(inc\.?|corp\.?|corporation|incorporated|plc)\b", re.I)


def _money(s: str) -> float:
    return float(s.replace(",", ""))


def scan_clauses(doc: Doc) -> list[dict]:
    findings: list[dict] = []
    if doc.kind != "contract":
        return findings
    text = doc.text
    for rid, pattern, sev, title, detail, action in CLAUSE_RULES:
        if pattern is None:
            continue
        m = re.search(pattern, text, re.I)
        if m:
            findings.append({
                "rule": rid, "severity": sev, "title": title, "detail": detail, "action": action,
                "evidence": text[max(0, m.start() - 60): m.end() + 60].replace("\n", " ").strip(),
                "doc": doc.name,
            })
    if not re.search(r"terminat\w+[^.]{0,80}(convenience|for any reason|without cause)", text, re.I):
        r = next(r for r in CLAUSE_RULES if r[0] == "missing_termination")
        findings.append({"rule": r[0], "severity": r[2], "title": r[3], "detail": r[4], "action": r[5],
                         "evidence": "", "doc": doc.name})
    return findings


def scan_invoices(docs: Iterable[Doc]) -> dict:
    """Aggregate spend per vendor and flag 1099-NEC exposure."""
    spend: dict[str, float] = defaultdict(float)
    count: dict[str, int] = defaultdict(int)
    is_corp: dict[str, bool] = {}
    for d in docs:
        if d.kind != "invoice":
            continue
        vm = VENDOR.search(d.text)
        vendor = (vm.group(1).strip().rstrip(".,") if vm else "Unknown vendor")
        tm = TOTAL.search(d.text)
        amt = _money(tm.group(1)) if tm else max((_money(m.group(1)) for m in MONEY.finditer(d.text)), default=0.0)
        spend[vendor] += amt
        count[vendor] += 1
        is_corp[vendor] = bool(ENTITY_WORDS.search(vendor))
    vendors = []
    findings = []
    for v, total in sorted(spend.items(), key=lambda kv: -kv[1]):
        needs_1099 = total >= NEC_THRESHOLD and not is_corp[v]
        vendors.append({"vendor": v, "total": round(total, 2), "invoices": count[v],
                        "likely_corporation": is_corp[v], "needs_1099_nec": needs_1099})
        if needs_1099:
            findings.append({
                "rule": "1099_nec", "severity": "high", "title": f"1099-NEC likely required: {v}",
                "detail": f"${total:,.2f} paid across {count[v]} invoice(s) exceeds the ${NEC_THRESHOLD:,.0f} reporting threshold "
                          "and the payee does not look like a corporation.",
                "action": "Collect a W-9 now; file 1099-NEC by Jan 31 (recipient copy) / IRS copy per current deadline.",
                "evidence": f"{v}: {count[v]} invoices", "doc": "invoices",
            })
        elif total >= NEC_THRESHOLD * 0.8 and not is_corp[v]:
            findings.append({
                "rule": "1099_watch", "severity": "medium", "title": f"Approaching 1099 threshold: {v}",
                "detail": f"${total:,.2f} so far; one more invoice likely crosses ${NEC_THRESHOLD:,.0f}.",
                "action": "Request a W-9 before the next payment.", "evidence": "", "doc": "invoices",
            })
    return {"vendors": vendors, "findings": findings}


def checklist(findings: list[dict], vendors: list[dict]) -> list[str]:
    items = []
    n1099 = [v for v in vendors if v["needs_1099_nec"]]
    if n1099:
        items.append(f"Collect W-9 from {len(n1099)} vendor(s): " + ", ".join(v["vendor"] for v in n1099))
        items.append("File Form 1099-NEC for each (recipient copy due Jan 31); e-file if 10+ information returns")
    if any(f["rule"] == "auto_renew" for f in findings):
        items.append("Calendar every auto-renewal cancellation deadline (notice window minus 7 days)")
    if any(f["severity"] == "high" and f["rule"] not in ("1099_nec",) for f in findings):
        items.append("Send redline requests for HIGH clause findings before signing / at renewal")
    items.append("Keep this report with the signed copy; re-run on any amendment")
    return items
