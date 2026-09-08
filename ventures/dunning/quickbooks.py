"""QuickBooks Online adapter.

The article's system "sits behind QuickBooks and notices when an invoice goes
unpaid".  QBO exposes that through one query endpoint.  Setup is a standard
OAuth2 app (client id/secret, redirect, refresh token); at runtime you need an
access token and the company's realm id.  `fetch_open_invoices` pulls every
invoice with a balance and `to_invoices` maps them - plus the customer's own
payment history, computed from their paid invoices - onto our Invoice model.
Everything here also works on a saved JSON export for demos and tests.
"""
from __future__ import annotations

import json
import os
from datetime import date
from typing import Optional

from .engine import CustomerHistory, Invoice

QBO_BASE = os.environ.get("QBO_BASE", "https://quickbooks.api.intuit.com")


def _query(access_token: str, realm_id: str, sql: str) -> dict:
    import httpx

    r = httpx.get(f"{QBO_BASE}/v3/company/{realm_id}/query", params={"query": sql, "minorversion": "73"},
                  headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"}, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_open_invoices(access_token: str, realm_id: str) -> dict:
    """Return {"open": [...], "paid": [...]} raw QBO invoice objects.
    'paid' covers the last 24 months so we can compute payment history."""
    open_ = _query(access_token, realm_id, "SELECT * FROM Invoice WHERE Balance > '0' MAXRESULTS 1000")
    paid = _query(access_token, realm_id, "SELECT * FROM Invoice WHERE Balance = '0' ORDERBY TxnDate DESC MAXRESULTS 1000")
    return {"open": open_.get("QueryResponse", {}).get("Invoice", []),
            "paid": paid.get("QueryResponse", {}).get("Invoice", [])}


def load_export(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def _paid_on(inv: dict) -> Optional[date]:
    # QBO links payments via LinkedTxn; exports often carry a flattened "PaidDate".
    if inv.get("PaidDate"):
        return date.fromisoformat(inv["PaidDate"][:10])
    for l in inv.get("LinkedTxn", []):
        if l.get("TxnType") == "Payment" and l.get("TxnDate"):
            return date.fromisoformat(l["TxnDate"][:10])
    return None


def histories(paid: list[dict], today: date | None = None) -> dict[str, CustomerHistory]:
    today = today or date.today()
    by: dict[str, list[dict]] = {}
    for inv in paid:
        by.setdefault(inv["CustomerRef"]["value"], []).append(inv)
    out = {}
    for cid, invs in by.items():
        lags = []
        first = today
        for inv in invs:
            due = date.fromisoformat(inv["DueDate"][:10])
            txn = date.fromisoformat(inv["TxnDate"][:10])
            first = min(first, txn)
            p = _paid_on(inv)
            if p:
                lags.append((p - due).days)
        out[cid] = CustomerHistory(
            invoices_paid=len(invs), avg_days_to_pay=round(sum(lags) / len(lags), 1) if lags else 0.0,
            late_count=sum(1 for l in lags if l >= 7), years_as_customer=round((today - first).days / 365, 1),
        )
    return out


def to_invoices(payload: dict, pay_url_template: str = "", today: date | None = None) -> list[Invoice]:
    hist = histories(payload.get("paid", []), today)
    out = []
    for inv in payload.get("open", []):
        cust = inv["CustomerRef"]
        email = (inv.get("BillEmail") or {}).get("Address", "")
        out.append(Invoice(
            id=inv.get("DocNumber") or inv["Id"], customer=cust.get("name", ""), email=email,
            amount=float(inv.get("Balance", inv.get("TotalAmt", 0))), due=date.fromisoformat(inv["DueDate"][:10]),
            currency=(inv.get("CurrencyRef") or {}).get("value", "USD"), phone=(inv.get("CustomerPhone") or ""),
            pay_url=(inv.get("InvoiceLink") or (pay_url_template.format(id=inv["Id"]) if pay_url_template else "")),
            history=hist.get(cust["value"], CustomerHistory()),
        ))
    return out


def detect_payments(previous: list[Invoice], payload: dict, today: date | None = None) -> list[tuple[Invoice, float]]:
    """Diff a fresh QBO pull against what we were chasing: anything that dropped out of
    'open' (or whose balance fell) was paid.  This is how recovered money is attributed."""
    today = today or date.today()
    now_open = {(i.get("DocNumber") or i["Id"]): float(i.get("Balance", 0)) for i in payload.get("open", [])}
    paid = []
    for inv in previous:
        bal = now_open.get(inv.id, 0.0)
        if bal < inv.amount:
            paid.append((inv, inv.amount - bal))
    return paid
