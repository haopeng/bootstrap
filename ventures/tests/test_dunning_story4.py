"""The four details from story 4: QuickBooks sync, history-aware tone, phone call that
understands 'next week', and 10%-of-recovered pricing."""
import os
from datetime import date, datetime

from ventures.dunning import quickbooks as qb, run_day
from ventures.dunning.engine import CustomerHistory, Invoice, parse_promise
from ventures.dunning.recovery import RecoveryLedger
from ventures.dunning.voice import DISCLOSURE, handle_transcript, script

EXPORT = os.path.join(os.path.dirname(__file__), "..", "samples", "dunning", "qbo_export.json")
TODAY = date(2026, 9, 8)  # a Tuesday


def test_quickbooks_history_and_profiles():
    invs = qb.to_invoices(qb.load_export(EXPORT), today=TODAY)
    by = {i.customer: i for i in invs}
    assert by["Acme Logistics"].history.profile() == "warm" and by["Acme Logistics"].history.invoices_paid == 8
    assert by["Studio Fischer"].history.profile() == "urgent" and by["Studio Fischer"].history.late_count == 3
    assert by["Haddad Wholesale"].history.profile() == "standard"  # no history yet
    assert by["Acme Logistics"].phone == "512-555-0301"


def test_tone_changes_cadence_and_wording(store):
    invs = qb.to_invoices(qb.load_export(EXPORT), today=TODAY)
    r = run_day(invs, "Sam", today=TODAY, utc_now=datetime(2026, 9, 8, 15, 0), store=store)
    steps = {s["invoice"]: s for s in r["sent"]}
    assert steps["INV-1088"]["profile"] == "urgent" and steps["INV-1088"]["step"] == "firm" and steps["INV-1088"]["call"] == "placed"
    assert steps["INV-1097"]["profile"] == "standard" and "call" not in steps["INV-1097"]
    events = list(store.events(r["job_id"]))
    bodies = [e["data"]["body"] for e in events if e["kind"] == "email_sent"]
    assert any("great customer for years" in b for b in bodies)   # warm opener
    assert any("run past due recently" in b for b in bodies)      # urgent closer
    calls = [e["data"] for e in events if e["kind"] == "call"]
    assert calls and calls[0]["script"].startswith("Hi, this is an automated assistant") and "I'm an AI" in calls[0]["script"]


def test_promise_parsing():
    assert parse_promise("we'll pay next week", TODAY) == date(2026, 9, 18)
    assert parse_promise("by Friday", TODAY) == date(2026, 9, 11)
    assert parse_promise("end of month", TODAY) == date(2026, 9, 30)
    assert parse_promise("on the 15th", TODAY) == date(2026, 9, 15)
    assert parse_promise("check goes out 9/20", TODAY) == date(2026, 9, 20)
    assert parse_promise("Sept 30th at the latest", TODAY) == date(2026, 9, 30)
    assert parse_promise("in 3 days", TODAY) == date(2026, 9, 11)
    assert parse_promise("no idea, sorry", TODAY) is None


def test_call_transcript_updates_invoice():
    inv = Invoice("X", "Studio Fischer", "l@x", 3400, date(2026, 8, 31), phone="1", history=CustomerHistory(3, 31.7, 3, 1.0))
    assert script(inv, TODAY, "Sam").startswith(DISCLOSURE.split("{")[0])
    r = handle_transcript(inv, "Sorry, our AP runs Thursdays, we'll pay next week.", TODAY, "Sam")
    assert r["intent"] == "promise" and inv.promise_date == date(2026, 9, 18) and "September 18" in r["closing_line"]
    from ventures.dunning.engine import next_step
    assert next_step(inv, date(2026, 9, 15)) is None          # waits for the promise
    assert next_step(inv, date(2026, 9, 19)) is not None      # resumes the day after
    inv2 = Invoice("Y", "A B", "a@b", 100, date(2026, 8, 31), phone="1")
    r = handle_transcript(inv2, "We never received this invoice and the amount is wrong.", TODAY, "Sam")
    assert r["intent"] == "dispute" and inv2.status == "disputed"
    inv3 = Invoice("Z", "A B", "a@b", 100, date(2026, 8, 31), phone="1")
    assert handle_transcript(inv3, "Stop calling us.", TODAY, "Sam")["status"] == "stopped"


def test_recovery_attribution_and_fee():
    led = RecoveryLedger()
    chased = Invoice("A", "C", "c@x", 3400, date(2026, 8, 31), sent_steps=["gentle", "firm"], last_touch=TODAY)
    r = led.record(chased, 3400, date(2026, 9, 17), chased.last_touch)
    assert r.attributed and r.fee == 340.0 and chased.status == "paid"
    early = Invoice("B", "C", "c@x", 1200, date(2026, 9, 11), sent_steps=["heads_up"], last_touch=TODAY)
    assert not led.record(early, 1200, date(2026, 9, 10), early.last_touch).attributed   # would have paid anyway
    stale = Invoice("C", "C", "c@x", 500, date(2026, 7, 1), sent_steps=["gentle", "firm", "final"], last_touch=date(2026, 7, 20))
    assert not led.record(stale, 500, date(2026, 9, 1), stale.last_touch).attributed   # too long after last touch
    onboarded = Invoice("D", "C", "c@x", 500, date(2026, 8, 1), sent_steps=["heads_up", "gentle", "firm"],
                        notes=["skipped heads_up: onboarded 20 days past due", "skipped gentle: onboarded 20 days past due"], last_touch=TODAY)
    assert led.record(onboarded, 500, date(2026, 9, 12), onboarded.last_touch).attributed  # 'firm' was really sent
    st = led.statement("2026-09")
    assert st["recovered"] == 3900 and st["fee_due"] == 390.0 and len(st["not_attributed"]) == 2


def test_detect_payments_from_resync():
    payload = qb.load_export(EXPORT)
    invs = qb.to_invoices(payload, today=TODAY)
    payload["open"] = [o for o in payload["open"] if o["DocNumber"] != "INV-1088"]
    payload["open"][0]["Balance"] = 200.0  # partial payment on INV-1101
    paid = qb.detect_payments(invs, payload, TODAY)
    assert {(i.id, amt) for i, amt in paid} == {("INV-1088", 3400.0), ("INV-1101", 1000.0)}
