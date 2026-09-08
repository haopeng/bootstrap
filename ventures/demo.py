"""End-to-end demo: runs every product on its sample data and writes the
deliverables to ventures/out/.  Works with or without Anthropic credentials."""
from __future__ import annotations

import glob
import json
import os
from datetime import date, datetime

from ventures.core import Store, get_llm, quote

HERE = os.path.dirname(__file__)
SAMPLES = os.path.join(HERE, "samples")
OUT = os.path.join(HERE, "out")
TODAY = date(2026, 9, 8)
NOW = datetime(2026, 9, 8, 15, 0)


def _write(name: str, text: str) -> str:
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    with open(path, "w") as f:
        f.write(text)
    return path


def run_all(store: Store | None = None, verbose: bool = True) -> dict[str, dict]:
    store = store or Store()
    results: dict[str, dict] = {}

    from ventures.taxguard import review as tax_review
    from ventures.taxguard.ingest import load_path
    docs = [load_path(p) for p in sorted(glob.glob(os.path.join(SAMPLES, "taxguard", "*")))]
    results["taxguard"] = tax_review(docs, store)

    from ventures.dealscout import run as deal_run
    from ventures.dealscout.compliance import ConsentLedger
    from ventures.dealscout.records import from_csv
    with open(os.path.join(SAMPLES, "dealscout", "county_records.csv")) as f:
        recs = from_csv(f.read())
    ledger = ConsentLedger()
    ledger.get("512-555-0142").national_dnc = False
    ledger.opt_in("512-555-0142", "owner replied YES to mailer")
    results["dealscout"] = deal_run(recs, "Sam Ortiz", "Ortiz Home Buyers", "512-555-0100", ledger, today=TODAY,
                                    store=store, local_now=NOW)

    from ventures.launchradar import scan
    with open(os.path.join(SAMPLES, "launchradar", "threads.json")) as f:
        threads = json.load(f)
    results["launchradar"] = scan(
        "Dunning", "Polite automatic invoice reminders for freelancers and small agencies. A 4-step overdue invoice "
        "follow-up sequence with a payment link, pauses on disputes, plugs into Stripe and QuickBooks.",
        threads=threads, store=store, now=1757300000)

    from ventures.dunning import handle_reply, run_day
    from ventures.dunning import quickbooks as qb
    from ventures.dunning.recovery import RecoveryLedger
    from ventures.dunning.voice import handle_transcript
    payload = qb.load_export(os.path.join(SAMPLES, "dunning", "qbo_export.json"))  # stands in for a live QBO pull
    invoices = qb.to_invoices(payload, today=TODAY)
    results["dunning"] = run_day(invoices, "Sam at Ortiz Studio", today=TODAY, utc_now=NOW, store=store)
    by_id = {i.id: i for i in invoices}
    results["dunning"]["replies"] = [
        handle_transcript(by_id["INV-1088"], "Sorry, our AP runs Thursdays, we'll pay next week.", TODAY, "Sam"),
        handle_reply(by_id["INV-1097"], "This is the wrong amount, we agreed on 800.", today=TODAY, store=store),
    ]
    ledger = RecoveryLedger()
    ledger.record(by_id["INV-1088"], 3400, date(2026, 9, 17), by_id["INV-1088"].last_touch)
    results["dunning"]["statement"] = ledger.statement("2026-09")
    results["dunning"]["report_md"] += (
        "\n## Call outcome\n\n" + results["dunning"]["replies"][0]["closing_line"]
        + f"\n\n## Fee statement (10% of attributed recoveries)\n\n{results['dunning']['statement']}\n")

    from ventures.reviewreply import run as rr_run
    with open(os.path.join(SAMPLES, "reviewreply", "reviews.json")) as f:
        reviews = json.load(f)
    results["reviewreply"] = rr_run(reviews, "Taquería Sol", "Luis", "luis@taqueriasol.example", store)

    from ventures.bidscout import run as bid_run
    from ventures.bidscout.engine import Profile
    with open(os.path.join(SAMPLES, "bidscout", "opportunities.json")) as f:
        opps = json.load(f)
    profile = Profile("Hill Country Grounds LLC", ["561730", "561720"], ["mowing", "irrigation", "landscap", "tree"],
                      ["TX"], ["SDVOSB", "SB"], max_value=1_000_000)
    results["bidscout"] = bid_run(profile, opps, today=TODAY, store=store)

    from ventures.leasecheck import review as lease_review
    with open(os.path.join(SAMPLES, "leasecheck", "lease.txt")) as f:
        results["leasecheck"] = lease_review(f.read(), "TX", "Bluebonnet team", store)

    for name, r in results.items():
        _write(f"{name}.md", r["report_md"])
    _write("bids.ics", results["bidscout"]["ics"])

    if verbose:
        llm = get_llm()
        mode = f"Claude ({llm.model})" if llm.available else "rules-only (no Anthropic credentials found)"
        print(f"Ran 7 products in {mode}. Reports in {OUT}/\n")
        for name, r in results.items():
            first = r["report_md"].split("\n\n")[1].split("\n")[0]
            plan = quote(name)[0]
            print(f"  {name:12s} {first[:95]}")
            price = f"${plan.price_usd:g} {plan.unit}" if plan.price_usd else plan.unit
            print(f"  {'':12s} price: {price}  est. model cost/unit: ${plan.est_llm_cost_usd:.2f}")
        if llm.available:
            u = llm.usage
            print(f"\nModel usage: {u.calls} calls, {u.input_tokens} in / {u.output_tokens} out, ≈ ${u.cost_usd:.3f}")
    return results


if __name__ == "__main__":
    run_all()
