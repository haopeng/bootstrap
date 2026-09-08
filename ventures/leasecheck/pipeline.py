from __future__ import annotations

from ventures.core import Store, get_llm, render_markdown

from . import engine

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "extra_findings": {"type": "array", "items": {"type": "object", "properties": {
            "title": {"type": "string"}, "severity": {"type": "string", "enum": ["high", "medium", "low", "info"]},
            "detail": {"type": "string"}, "action": {"type": "string"}, "evidence": {"type": "string"}},
            "required": ["title", "severity", "detail", "action", "evidence"], "additionalProperties": False}},
    },
    "required": ["summary", "extra_findings"], "additionalProperties": False,
}


def review(text: str, state: str = "", landlord: str = "there", store: Store | None = None) -> dict:
    store = store or Store()
    jid = store.new_job("leasecheck", "review", {"state": state, "chars": len(text)})
    findings = engine.scan(text)
    terms = engine.key_terms(text)
    summary = (f"Rent ${terms['monthly_rent']}/mo, deposit ${terms['deposit']}, {terms['term_months']}-month term. "
               f"{len(findings)} clause(s) flagged, {sum(f['severity']=='high' for f in findings)} high.")
    llm = get_llm()
    if llm.available:
        out = llm.json(SCHEMA, f"State: {state or 'unknown'}. Tenant-side review. Already flagged: "
                       f"{[f['title'] for f in findings]}.\n<lease>\n{text}\n</lease>",
                       system="You explain residential leases to tenants in plain English. Not legal advice; flag what to negotiate.", effort="medium")
        if out:
            findings += [{**f, "rule": "llm"} for f in out["extra_findings"]]
            summary += "\n\n" + out["summary"]
    sections = {"Key terms": terms}
    if state.upper() in engine.STATE_NOTES:
        sections[f"{state.upper()} tenant rules to know"] = engine.STATE_NOTES[state.upper()]
    email = engine.negotiation_email(findings, landlord)
    if email:
        sections["Negotiation email (copy/paste)"] = email
    report = render_markdown("LeaseCheck review", summary, findings, sections,
                             "LeaseCheck is not a law firm. For eviction, discrimination or habitability disputes contact a local tenant-rights organization.")
    result = {"job_id": jid, "findings": findings, "terms": terms, "email": email, "report_md": report}
    store.finish(jid, {"findings": findings, "terms": terms})
    return result
