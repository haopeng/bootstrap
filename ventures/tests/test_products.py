import json
import os
from datetime import date, datetime

import pytest

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "samples")


def test_taxguard_flags_clauses_and_1099(store):
    from ventures.taxguard import review
    from ventures.taxguard.ingest import load_path
    import glob
    docs = [load_path(p) for p in sorted(glob.glob(os.path.join(SAMPLES, "taxguard", "*")))]
    r = review(docs, store)
    rules = {f["rule"] for f in r["findings"]}
    assert {"auto_renew", "unlimited_indemnity", "unilateral_change", "1099_nec", "missing_termination"} <= rules
    v = {x["vendor"]: x for x in r["vendors"]}
    assert v["Maria Delgado Design"]["needs_1099_nec"] is True
    assert v["Quantum Data Services, Inc"]["needs_1099_nec"] is False  # corporation
    assert "Collect W-9" in r["checklist"][0]
    assert store.get(r["job_id"])["status"] == "done"


def test_dealscout_scores_and_gates(store):
    from ventures.dealscout import run
    from ventures.dealscout.compliance import ConsentLedger, can_contact
    from ventures.dealscout.records import from_csv
    with open(os.path.join(SAMPLES, "dealscout", "county_records.csv")) as f:
        recs = from_csv(f.read())
    ledger = ConsentLedger()
    r = run(recs, "S", "Co", "555", ledger, today=date(2026, 9, 8), store=store, local_now=datetime(2026, 9, 8, 14, 0))
    assert r["leads"][0]["address"] == "418 Maple Ave" and r["leads"][0]["absentee"] is True
    assert r["leads"][1]["absentee"] is False
    # No consent, no scrub -> every automated contact blocked; mail always allowed.
    auto = [e for e in r["outreach_log"] if e["channel"] in ("sms", "ai_voice")]
    assert auto and all(not e["allowed"] for e in auto)
    assert all(e["allowed"] for e in r["outreach_log"] if e["channel"] == "mail")
    # Quiet hours + DNC.
    ledger.get("1").national_dnc = False
    ledger.opt_in("1", "test")
    assert can_contact("ai_voice", "1", ledger, datetime(2026, 9, 8, 22, 0))[0] is False
    assert can_contact("ai_voice", "1", ledger, datetime(2026, 9, 8, 12, 0))[0] is True
    ledger.opt_out("1")
    assert can_contact("sms", "1", ledger, datetime(2026, 9, 8, 12, 0))[0] is False
    # Every AI voice script discloses.
    assert all("I'm an AI" in p["voice_script"] for p in r["packets"].values())


def test_dealscout_reply_never_unstops():
    from ventures.dealscout.llm import classify_reply
    assert classify_reply("please STOP contacting me")["intent"] == "stop"
    assert classify_reply("Yes, how much would you offer?")["intent"] == "interested"


def test_launchradar_ranks_and_discloses(store):
    from ventures.launchradar import approve, scan
    with open(os.path.join(SAMPLES, "launchradar", "threads.json")) as f:
        threads = json.load(f)
    r = scan("Dunning", "Automatic polite invoice reminders and overdue invoice follow-up for freelancers.", threads=threads, store=store, now=1757300000)
    ids = [q["thread_id"] for q in r["queue"]]
    assert "hn:1001" in ids and "hn:1002" not in ids  # game engine thread filtered out
    assert all("I built" in q["reply"] for q in r["queue"])
    assert all(q["status"] == "needs_approval" for q in r["queue"])
    q = approve(store, r["job_id"], ids[0], edited_reply="edited")
    assert q["status"] == "approved" and q["reply"] == "edited"


def test_dunning_sequence_and_guardrails(store):
    from ventures.dunning import handle_reply, run_day
    from ventures.dunning.engine import Invoice, next_step
    from ventures.dunning.messages import BANNED, compose
    today = date(2026, 9, 8)
    late = Invoice("A", "Lena F", "l@x", 3400, date(2026, 8, 31), late_fee_allowed=True, late_fee_pct=1.5)
    assert next_step(late, today)[0] == "firm" and "heads_up" in late.sent_steps
    no_fee = Invoice("B", "Ben C", "b@x", 850, date(2026, 8, 31))
    assert compose(no_fee, "firm", today, "S")["late_fee"] == 0
    assert compose(late, "firm", today, "S")["late_fee"] == 51.0
    for step in ("heads_up", "gentle", "firm", "final"):
        assert not BANNED.search(compose(late, step, today, "S")["body"])
    # Business hours: 15:00 UTC is 05:00 in UTC-10 -> deferred.
    hawaii = Invoice("C", "Kai W", "k@x", 200, date(2026, 9, 7), tz_offset_hours=-10)
    r = run_day([hawaii], "S", today=today, utc_now=datetime(2026, 9, 8, 15, 0), store=store)
    assert r["skipped"] and not r["sent"]
    old = Invoice("D", "Omar H", "o@x", 560, date(2026, 7, 20))
    r = run_day([old], "S", today=today, utc_now=datetime(2026, 9, 8, 15, 0), store=store)
    assert r["handoff"] == ["D"] and old.status == "handoff"
    # Replies.
    inv = Invoice("E", "X Y", "x@y", 100, date(2026, 9, 1))
    assert handle_reply(inv, "this is the wrong amount", today, store)["status"] == "disputed"
    inv2 = Invoice("F", "X Y", "x@y", 100, date(2026, 9, 1))
    assert handle_reply(inv2, "STOP emailing me", today, store)["status"] == "stopped"
    assert next_step(inv2, today) is None


def test_reviewreply_safe_and_urgent(store):
    from ventures.reviewreply import run
    from ventures.reviewreply.engine import safe
    with open(os.path.join(SAMPLES, "reviewreply", "reviews.json")) as f:
        reviews = json.load(f)
    r = run(reviews, "Biz", "Luis", "l@biz", store)
    by = {d["id"]: d for d in r["drafts"]}
    assert by["y1"]["urgent"] and by["g1"]["sentiment"] == "positive"
    assert all(safe(d["reply"]) for d in r["drafts"])
    assert not safe("You're wrong, that never happened.")
    assert not safe("As our patient you know we care.")


def test_bidscout_matching_and_ics(store):
    from ventures.bidscout import run
    from ventures.bidscout.engine import Profile
    with open(os.path.join(SAMPLES, "bidscout", "opportunities.json")) as f:
        opps = json.load(f)
    p = Profile("HCG", ["561730", "561720"], ["mowing", "irrigation", "landscap", "tree"], ["TX"], ["SDVOSB", "SB"], max_value=1_000_000)
    r = run(p, opps, today=date(2026, 9, 8), store=store)
    dec = {m["id"]: m["decision"] for m in r["matched"]}
    assert dec["n1"] == "GO" and dec["n5"] == "NO-GO" and dec["n4"] != "GO"
    assert "BEGIN:VEVENT" in r["ics"] and "n1@bidscout" in r["ics"]


def test_leasecheck(store):
    from ventures.leasecheck import review
    with open(os.path.join(SAMPLES, "leasecheck", "lease.txt")) as f:
        r = review(f.read(), "TX", "Bluebonnet team", store)
    rules = {f["rule"] for f in r["findings"]}
    assert {"nonrefundable_deposit", "entry_notice", "waiver", "repairs_tenant", "late_fee"} <= rules
    assert r["terms"]["monthly_rent"] == "1,950.00"
    assert "24 hours written notice" in r["email"]


def test_pricing_margins():
    from ventures.core import PRICING
    for plans in PRICING.values():
        for p in plans:
            if p.price_usd:
                assert p.est_llm_cost_usd / p.price_usd < 0.25, f"{p.product}/{p.name} margin too thin"


def test_demo_runs_end_to_end(store, tmp_path, monkeypatch):
    import ventures.demo as demo
    monkeypatch.setattr(demo, "OUT", str(tmp_path / "out"))
    results = demo.run_all(store, verbose=False)
    assert set(results) == {"taxguard", "dealscout", "launchradar", "dunning", "reviewreply", "bidscout", "leasecheck"}
    assert (tmp_path / "out" / "bids.ics").exists()


def test_server_smoke():
    from fastapi.testclient import TestClient
    from ventures.server import app
    c = TestClient(app)
    assert c.get("/healthz").json()["ok"]
    assert "Seven small AI businesses" in c.get("/").text
    assert "Pricing" in c.get("/leasecheck").text
    r = c.post("/api/leasecheck", data={"text": "Tenant waives the right to a jury trial. Late fee of $150 plus $25 per day.", "state": "NY"})
    assert r.status_code == 200 and "Waiver of rights" in r.text and "NY tenant rules" in r.text
    with open(os.path.join(SAMPLES, "taxguard", "vendor_agreement.txt"), "rb") as f:
        r = c.post("/api/taxguard", files=[("files", ("vendor_agreement.txt", f, "text/plain"))])
    assert r.status_code == 200 and "Automatic renewal" in r.text
