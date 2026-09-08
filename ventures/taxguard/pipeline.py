from __future__ import annotations

from ventures.core import Store, render_markdown

from . import engine, llm
from .ingest import Doc

DISCLAIMER = ("TaxGuard is software, not a law or accounting firm. This report is informational; "
              "confirm filings with a CPA and contract changes with counsel.")


def review(docs: list[Doc], store: Store | None = None) -> dict:
    """End to end: documents -> findings -> markdown report + checklist."""
    store = store or Store()
    jid = store.new_job("taxguard", "review", [d.name for d in docs])
    findings: list[dict] = []
    llm_summaries: list[str] = []
    redlines: dict[str, str] = {}

    for d in docs:
        rule_f = engine.scan_clauses(d)
        findings.extend(rule_f)
        enriched = llm.enrich(d.name, d.text, rule_f) if d.kind == "contract" else None
        if enriched:
            store.log(jid, "llm_enriched", {"doc": d.name, "n": len(enriched["findings"])})
            for f in enriched["findings"]:
                f["doc"] = d.name
                f["rule"] = "llm"
            findings.extend(enriched["findings"])
            llm_summaries.append(f"**{d.name}**: {enriched['summary']}")
            redlines[d.name] = enriched["redline_email"]

    inv = engine.scan_invoices(docs)
    findings.extend(inv["findings"])
    todo = engine.checklist(findings, inv["vendors"])

    high = sum(1 for f in findings if f["severity"] == "high")
    summary = (f"Reviewed {len(docs)} document(s): {sum(1 for d in docs if d.kind == 'contract')} contract(s), "
               f"{sum(1 for d in docs if d.kind == 'invoice')} invoice(s). "
               f"{len(findings)} finding(s), {high} high severity.")
    if llm_summaries:
        summary += "\n\n" + "\n\n".join(llm_summaries)

    sections: dict = {"Filing checklist": todo}
    if inv["vendors"]:
        sections["Vendor spend (1099 tracker)"] = [
            f"{v['vendor']}: ${v['total']:,.2f} over {v['invoices']} invoice(s)"
            + (" — 1099-NEC required" if v["needs_1099_nec"] else "") for v in inv["vendors"]]
    for name, email in redlines.items():
        sections[f"Redline request draft — {name}"] = email

    report = render_markdown("TaxGuard review", summary, findings, sections, DISCLAIMER)
    result = {"job_id": jid, "findings": findings, "vendors": inv["vendors"], "checklist": todo, "report_md": report}
    store.finish(jid, {k: v for k, v in result.items() if k != "report_md"})
    return result
