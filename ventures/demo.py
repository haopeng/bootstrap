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
    from ventures.dunning.engine import Invoice
    invoices = [
        Invoice("INV-101", "Priya Shah", "priya@acme.example", 1200, date(2026, 9, 11), pay_url="https://pay.example/101"),
        Invoice("INV-097", "Ben Carter", "ben@northco.example", 850, date(2026, 9, 7), pay_url="https://pay.example/097"),
        Invoice("INV-088", "Lena Fischer", "lena@studio.example", 3400, date(2026, 8, 31), late_fee_allowed=True,
                late_fee_pct=1.5, pay_url="https://pay.example/088"),
        Invoice("INV-070", "Omar Haddad", "omar@haddad.example", 560, date(2026, 7, 20), pay_url="https://pay.example/070"),
        Invoice("INV-099", "Kai Wong", "kai@wong.example", 200, date(2026, 9, 7), tz_offset_hours=-10, pay_url="https://pay.example/099"),
    ]
    results["dunning"] = run_day(invoices, "Sam at Ortiz Studio", today=TODAY, utc_now=NOW, store=store)
    results["dunning"]["replies"] = [
        handle_reply(invoices[2], "This is the wrong amount, we agreed on 3000.", today=TODAY, store=store),
        handle_reply(invoices[1], "Sorry, will pay by Friday", today=TODAY, store=store),
    ]

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
            print(f"  {'':12s} price: ${plan.price_usd:g} {plan.unit}  est. model cost/unit: ${plan.est_llm_cost_usd:.2f}")
        if llm.available:
            u = llm.usage
            print(f"\nModel usage: {u.calls} calls, {u.input_tokens} in / {u.output_tokens} out, ≈ ${u.cost_usd:.3f}")
    return results


if __name__ == "__main__":
    run_all()
