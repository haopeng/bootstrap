"""Message templates + Claude polish.  Hard rules that no model output may break:
no threats, no mention of credit reporting / legal action / collections, no
contacting anyone but the customer, late fee only if allowed."""
from __future__ import annotations

import re
from datetime import date

from ventures.core import get_llm

from .engine import Invoice, late_fee

TEMPLATES = {
    "heads_up": ("Heads-up: invoice {id} is due {due}",
                 "Hi {first},\n\nA quick heads-up that invoice {id} for {amount} is due on {due}. "
                 "You can pay online here: {pay_url}\n\nIf it's already scheduled, please ignore this. Thanks!\n\n{sender}"),
    "gentle": ("Invoice {id} — friendly reminder",
               "Hi {first},\n\nJust a friendly reminder that invoice {id} for {amount} was due on {due}. "
               "Pay here whenever convenient: {pay_url}\n\nIf you have any questions about the invoice, reply and I'll sort it out.\n\n{sender}"),
    "firm": ("Invoice {id} is {days} days past due",
             "Hi {first},\n\nInvoice {id} for {amount} is now {days} days past due.{fee_line} "
             "Could you let me know when we can expect payment, or if something is holding it up?\n\n{pay_url}\n\n{sender}"),
    "final": ("Action needed: invoice {id} ({days} days past due)",
              "Hi {first},\n\nInvoice {id} for {amount} is {days} days past due and I haven't heard back.{fee_line} "
              "Please pay by {deadline} or reply with a date that works so we can keep the account in good standing.\n\n{pay_url}\n\n{sender}"),
}

BANNED = re.compile(r"\b(lawsuit|legal action|attorney|sue|credit (report|bureau)|collections? agency|garnish|police|arrest)\b", re.I)

POLISH_SCHEMA = {"type": "object", "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
                 "required": ["subject", "body"], "additionalProperties": False}


def compose(inv: Invoice, step: str, today: date, sender: str, voice: str = "") -> dict:
    fee = late_fee(inv, today)
    fee_line = f" Per our terms a late fee of {inv.currency} {fee:,.2f} now applies." if fee else ""
    ctx = dict(id=inv.id, first=inv.customer.split()[0], amount=f"{inv.currency} {inv.amount:,.2f}",
               due=inv.due.strftime("%b %d"), days=(today - inv.due).days, pay_url=inv.pay_url or "(payment link)",
               sender=sender, fee_line=fee_line, deadline=date.fromordinal(today.toordinal() + 5).strftime("%b %d"))
    subject, body = (t.format(**ctx) for t in TEMPLATES[step])
    llm = get_llm()
    if llm.available and voice:
        out = llm.json(POLISH_SCHEMA,
                       f"Rewrite this payment reminder in this brand voice: '{voice}'. Keep every fact, link and amount. "
                       f"Never threaten, never mention legal action, credit reporting or collections.\n\nSubject: {subject}\n\n{body}",
                       effort="low")
        if out and not BANNED.search(out["body"]) and (inv.pay_url in out["body"] or not inv.pay_url):
            subject, body = out["subject"], out["body"]
    assert not BANNED.search(body), "template violated tone rules"
    return {"to": inv.email, "subject": subject, "body": body, "step": step, "late_fee": fee}


def send_email(msg: dict, log) -> dict:
    """Transport stub.  Production: SMTP/Postmark/SES.  Logs instead of sending."""
    entry = {**msg, "transport": "email (stub)", "sent": True}
    log("email_sent", entry)
    return entry
