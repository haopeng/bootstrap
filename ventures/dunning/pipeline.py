from __future__ import annotations

from datetime import date, datetime

from ventures.core import Store, get_llm, render_markdown

from . import engine, messages
from .engine import Invoice

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["paid_claim", "dispute", "stop", "promise", "other"]},
        "promise_date": {"type": ["string", "null"], "description": "ISO date if the customer named one"},
        "summary": {"type": "string"},
    },
    "required": ["intent", "promise_date", "summary"], "additionalProperties": False,
}


def run_day(invoices: list[Invoice], sender: str, today: date | None = None, utc_now: datetime | None = None,
            voice: str = "", store: Store | None = None) -> dict:
    """One scheduler tick: decide what each open invoice needs today and send it (if business hours)."""
    store = store or Store()
    today = today or date.today()
    utc_now = utc_now or datetime.utcnow()
    jid = store.new_job("dunning", "tick", {"date": today.isoformat(), "invoices": len(invoices)})
    sent, skipped, handoff = [], [], []
    for inv in invoices:
        step = engine.next_step(inv, today)
        if not step:
            continue
        name, tone = step
        if name == "handoff":
            inv.status = "handoff"
            handoff.append(inv.id)
            store.log(jid, "handoff", {"invoice": inv.id, "amount": inv.amount})
            continue
        if not engine.in_business_hours(utc_now, inv.tz_offset_hours):
            skipped.append((inv.id, name, "outside customer business hours; retry next tick"))
            continue
        msg = messages.compose(inv, name, today, sender, voice)
        messages.send_email(msg, lambda k, d: store.log(jid, k, {"invoice": inv.id, **d}))
        inv.sent_steps.append(name)
        sent.append({"invoice": inv.id, "step": name, "subject": msg["subject"], "late_fee": msg["late_fee"]})

    open_total = sum(i.amount for i in invoices if i.status == "open")
    findings = [{"severity": "info", "title": f"{s['invoice']}: sent '{s['step']}'", "detail": s["subject"],
                 "action": f"late fee applied: {s['late_fee']}" if s["late_fee"] else ""} for s in sent]
    findings += [{"severity": "high", "title": f"{h}: 30+ days — needs a human decision",
                  "detail": "Automated sequence complete.", "action": "Call the customer; offer a payment plan; decide on write-off or a licensed agency."} for h in handoff]
    findings += [{"severity": "low", "title": f"{i}: '{n}' deferred", "detail": why, "action": ""} for i, n, why in skipped]
    report = render_markdown(
        f"Dunning — daily run {today.isoformat()}",
        f"{len(invoices)} invoices tracked; {len(sent)} reminders sent; {len(handoff)} handed to you; "
        f"{len(skipped)} deferred. Open balance: ${open_total:,.2f}.",
        findings, {}, "Dunning sends first-party reminders for your own invoices only. It is not a debt collector.")
    store.finish(jid, {"sent": sent, "handoff": handoff, "skipped": skipped})
    return {"job_id": jid, "sent": sent, "handoff": handoff, "skipped": skipped, "report_md": report}


def handle_reply(inv: Invoice, text: str, today: date | None = None, store: Store | None = None) -> dict:
    """Inbound email/SMS from the customer: triage, update invoice state, tell the human what happened."""
    store = store or Store()
    today = today or date.today()
    rules = engine.triage(text)
    intent, promise = rules["intent"], None
    llm = get_llm()
    if llm.available:
        out = llm.json(REPLY_SCHEMA, f"Customer reply to an invoice reminder:\n\n{text}", effort="low")
        if out:
            # Rules win on the safety-critical intents; the model refines the rest.
            if intent not in ("stop", "dispute"):
                intent = out["intent"]
            if out["promise_date"]:
                try:
                    promise = date.fromisoformat(out["promise_date"])
                except ValueError:
                    promise = None
    engine.apply_triage(inv, intent, today, promise)
    result = {"invoice": inv.id, "intent": intent, "status": inv.status, "promise_date": inv.promise_date,
              "action": engine.triage(text)["action"] if intent == rules["intent"] else "See model summary"}
    jid = store.new_job("dunning", "reply", {"invoice": inv.id, "text": text})
    store.finish(jid, result)
    return result
