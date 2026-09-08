from __future__ import annotations

from datetime import date, datetime

from ventures.core import Store, render_markdown

from . import engine, llm, outreach
from .compliance import ConsentLedger
from .records import Record


def run(records: list[Record], sender: str, company: str, phone: str, ledger: ConsentLedger | None = None,
        today: date | None = None, top_n: int = 10, store: Store | None = None,
        local_now: datetime | None = None) -> dict:
    """records -> ranked leads -> outreach packets (mail sent, sms/voice gated) -> deal memos."""
    store = store or Store()
    ledger = ledger or ConsentLedger()
    today = today or date.today()
    local_now = local_now or datetime.now()
    jid = store.new_job("dealscout", "scan", {"records": len(records), "company": company})

    leads = engine.build_leads(records, today)[:top_n]
    outreach_log: list[dict] = []
    log = lambda kind, data: (store.log(jid, kind, data), outreach_log.append(data))
    packets = {}
    memos = {}
    for lead in leads:
        pkt = outreach.draft(lead, sender, company, phone, datetime.combine(today, datetime.min.time()))
        packets[lead["key"]] = pkt
        outreach.send("mail", lead, pkt, ledger, local_now, log)
        for ch in ("sms", "ai_voice"):
            outreach.send(ch, lead, pkt, ledger, local_now, log)
        math = engine.deal_math(lead)
        memos[lead["key"]] = {**math, **llm.deal_memo(lead, math)}

    sent_mail = sum(1 for e in outreach_log if e["channel"] == "mail" and e["allowed"])
    blocked = [e for e in outreach_log if not e["allowed"]]
    findings = [{
        "severity": "high" if l["score"] >= 75 else "medium" if l["score"] >= 50 else "low",
        "title": f"{l['address']} ({l['city']}) — score {l['score']}",
        "detail": f"signals: {', '.join(l['signals'])}; absentee: {l['absentee']}; equity ratio {l['equity_ratio']}; "
                  f"max offer ${memos[l['key']]['max_offer']:,.0f}",
        "action": memos[l["key"]]["memo"], "evidence": l["notes"],
    } for l in leads]
    report = render_markdown(
        f"DealScout — {company} daily lead sheet ({today.isoformat()})",
        f"{len(records)} public records → {len(leads)} ranked leads. {sent_mail} letters queued for mail; "
        f"{len(blocked)} automated contacts blocked by the compliance gate (see log).",
        findings,
        {"Compliance log": [f"{e['channel']} → {e['address']}: {'sent' if e['allowed'] else 'BLOCKED'} ({e['reason']})" for e in outreach_log]},
        "DealScout finds and ranks public-record leads. It never places AI voice calls or texts without documented consent and a DNC scrub.",
    )
    result = {"job_id": jid, "leads": leads, "packets": packets, "memos": memos, "outreach_log": outreach_log, "report_md": report}
    store.finish(jid, {"leads": leads, "memos": memos, "outreach_log": outreach_log})
    return result
