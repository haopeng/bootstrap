"""Phone step.  The article's AI "calls the customer, understands 'we'll pay next
week', remembers it and updates the due date".  This module produces the call
script (with AI disclosure up front), and turns the transcript into an invoice
update.  Transport is a stub for Twilio Voice + a TTS/STT provider; the logic
that matters - what is said and what is done with the answer - is real."""
from __future__ import annotations

from datetime import date

from ventures.core import get_llm

from . import engine
from .engine import Invoice

DISCLOSURE = ("Hi, this is an automated assistant calling for {sender}. I'm an AI, not a person, "
              "and this call may be recorded. I'm calling about invoice {id} for {amount}, which was due {due}. ")

SCRIPT = {
    "warm": DISCLOSURE + "You've always been great about paying, so I just wanted to check it hasn't slipped through. "
                         "Is it already scheduled, or is there anything you need from us?",
    "standard": DISCLOSURE + "Could you tell me when we can expect payment, or if there's a question about the invoice?",
    "urgent": DISCLOSURE + "It's now {days} days past due and I need a payment date today, or to hear about any issue with "
                           "the invoice so {sender} can resolve it. When can we expect payment?",
}
CLOSE = {"promise": "Thank you — I've noted {date}. You'll get a confirmation by email, and we won't call again before then.",
         "dispute": "Understood — I'll pause all reminders and {sender} will review this and get back to you within a business day.",
         "paid_claim": "Great, thank you. We'll check for it and confirm by email; sorry for the crossed wires.",
         "stop": "Understood. We'll stop automated calls and emails; {sender} will follow up personally.",
         "other": "Thanks. I'll pass that along to {sender}, who will follow up by email."}

CALL_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["promise", "dispute", "paid_claim", "stop", "other"]},
        "promise_date": {"type": ["string", "null"]},
        "summary": {"type": "string"},
    },
    "required": ["intent", "promise_date", "summary"], "additionalProperties": False,
}


def script(inv: Invoice, today: date, sender: str) -> str:
    return SCRIPT[inv.history.profile()].format(sender=sender, id=inv.id, amount=f"{inv.currency} {inv.amount:,.2f}",
                                                due=inv.due.strftime("%B %d"), days=(today - inv.due).days)


def handle_transcript(inv: Invoice, transcript: str, today: date, sender: str) -> dict:
    """What the customer said -> what we do.  Rules decide the safety-critical intents
    (stop, dispute) and the date; the model refines the rest and the summary."""
    rules = engine.triage(transcript)
    intent = rules["intent"]
    promise = engine.parse_promise(transcript, today)
    summary = transcript.strip()[:200]
    llm = get_llm()
    if llm.available and intent not in ("stop", "dispute"):
        out = llm.json(CALL_SCHEMA, f"Today is {today.isoformat()}. Customer said on a payment call:\n\n{transcript}", effort="low")
        if out:
            intent = out["intent"]
            summary = out["summary"]
            if not promise and out["promise_date"]:
                try:
                    promise = date.fromisoformat(out["promise_date"])
                except ValueError:
                    promise = None
    if intent == "promise" and not promise:
        intent = "other"
    engine.apply_triage(inv, intent, today, promise)
    inv.notes.append(f"call {today.isoformat()}: {intent} — {summary}")
    return {"invoice": inv.id, "intent": intent, "promise_date": inv.promise_date, "status": inv.status,
            "closing_line": CLOSE[intent].format(sender=sender, date=inv.promise_date.strftime("%A, %B %d") if inv.promise_date else "")}


def place_call(inv: Invoice, today: date, sender: str, log) -> dict:
    """Transport stub: Twilio Voice -> streaming STT -> handle_transcript -> TTS.
    Only business lines from the accounting system are dialed, only in business hours
    (checked by the pipeline), and the first sentence is always the AI disclosure."""
    if not inv.phone:
        entry = {"invoice": inv.id, "placed": False, "reason": "no phone on file"}
    else:
        entry = {"invoice": inv.id, "placed": True, "to": inv.phone, "script": script(inv, today, sender), "transport": "twilio.voice (stub)"}
    log("call", entry)
    return entry
