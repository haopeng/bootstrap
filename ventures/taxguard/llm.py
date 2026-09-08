"""Claude layer: reads the whole document, explains flagged clauses in plain
English, catches things the regexes cannot, and drafts the redline requests."""
from __future__ import annotations

from ventures.core import get_llm

SYSTEM = """You review commercial contracts and vendor invoices for a US small business owner.
You are not their lawyer or CPA; be concrete and practical, cite the clause text you rely on,
and say 'confirm with counsel/CPA' only where it is genuinely warranted.
Prefer fewer, higher-impact findings over exhaustive lists."""

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "3-5 sentence plain-English summary of the risk picture"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "severity": {"type": "string", "enum": ["high", "medium", "low", "info"]},
                    "detail": {"type": "string"},
                    "action": {"type": "string"},
                    "evidence": {"type": "string", "description": "verbatim quote from the document"},
                },
                "required": ["title", "severity", "detail", "action", "evidence"],
                "additionalProperties": False,
            },
        },
        "redline_email": {"type": "string", "description": "short email to the counterparty requesting the top changes"},
    },
    "required": ["summary", "findings", "redline_email"],
    "additionalProperties": False,
}


def enrich(doc_name: str, text: str, rule_findings: list[dict]) -> dict | None:
    llm = get_llm()
    if not llm.available:
        return None
    prompt = (
        f"Document: {doc_name}\n\nRule-based findings already detected (avoid duplicating; refine or add):\n"
        + "\n".join(f"- {f['title']}: {f['evidence'][:120]}" for f in rule_findings)
        + "\n\n<document>\n" + text + "\n</document>"
    )
    return llm.json(SCHEMA, prompt, system=SYSTEM, effort="medium")
