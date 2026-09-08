from __future__ import annotations

from datetime import date

from ventures.core import Store, get_llm, render_markdown

from . import engine
from .engine import Profile

MEMO_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}, "requirements": {"type": "array", "items": {"type": "string"}},
                   "risks": {"type": "array", "items": {"type": "string"}}, "recommendation": {"type": "string"}},
    "required": ["summary", "requirements", "risks", "recommendation"], "additionalProperties": False,
}


def memo(opp: dict, profile: Profile) -> dict:
    fallback = {"summary": opp["description"][:300] or opp["title"], "requirements": ["Read the full solicitation for scope, bonding and insurance"],
                "risks": [r for r in opp["reasons"] if "not eligible" in r or "days" in r or "above" in r] or ["none flagged by rules"],
                "recommendation": opp["decision"]}
    llm = get_llm()
    if not llm.available:
        return fallback
    return llm.json(MEMO_SCHEMA, f"Contractor: {profile.company}, NAICS {profile.naics}, certs {profile.certifications}.\n"
                    f"Opportunity: {opp['title']} ({opp['agency']}) set-aside: {opp['set_aside']} deadline {opp['deadline']}\n"
                    f"<description>{opp['description'][:6000]}</description>\nWrite a go/no-go memo.", effort="medium") or fallback


def run(profile: Profile, opps: list[dict], today: date | None = None, store: Store | None = None) -> dict:
    store = store or Store()
    today = today or date.today()
    jid = store.new_job("bidscout", "scan", {"company": profile.company, "opps": len(opps)})
    matched = sorted((engine.match(profile, o, today) for o in opps), key=lambda m: -m["score"])
    shortlist = [m for m in matched if m["decision"] != "NO-GO"]
    memos = {m["id"]: memo(m, profile) for m in shortlist}
    findings = [{"severity": "high" if m["decision"] == "GO" else "medium", "title": f"[{m['decision']}] {m['title']} — {m['agency']}",
                 "detail": "; ".join(m["reasons"]), "action": f"Due {m['deadline']} · {m['url']} · {memos[m['id']]['recommendation']}"}
                for m in shortlist]
    report = render_markdown(
        f"BidScout — {profile.company} ({today.isoformat()})",
        f"{len(opps)} opportunities screened, {len(shortlist)} worth a look ({sum(m['decision']=='GO' for m in shortlist)} GO).",
        findings, {"Deadline calendar": "attached as bids.ics"}, "Always read the full solicitation; BidScout screens, it does not bid.")
    result = {"job_id": jid, "matched": matched, "shortlist": shortlist, "memos": memos, "ics": engine.ics(shortlist, profile.company), "report_md": report}
    store.finish(jid, {"shortlist": shortlist, "memos": memos})
    return result
