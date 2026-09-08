"""Render a findings dict as Markdown.  Every product's deliverable goes through here
so customers get one consistent document shape."""
from __future__ import annotations

from typing import Any


def _sev_icon(sev: str) -> str:
    return {"high": "🔴", "medium": "🟠", "low": "🟡", "info": "🔵"}.get(sev, "⚪")


def render_markdown(title: str, summary: str, findings: list[dict], sections: dict[str, Any] | None = None,
                    disclaimer: str = "") -> str:
    out = [f"# {title}", "", summary, ""]
    if findings:
        out.append("## Findings")
        out.append("")
        for f in sorted(findings, key=lambda x: {"high": 0, "medium": 1, "low": 2, "info": 3}.get(x.get("severity", "info"), 9)):
            out.append(f"- {_sev_icon(f.get('severity', 'info'))} **{f.get('title', 'Finding')}** — {f.get('detail', '')}")
            if f.get("action"):
                out.append(f"  - Action: {f['action']}")
            if f.get("evidence"):
                out.append(f"  - Evidence: `{str(f['evidence'])[:200]}`")
        out.append("")
    for name, body in (sections or {}).items():
        out.append(f"## {name}")
        out.append("")
        if isinstance(body, list):
            out.extend(f"- {item}" for item in body)
        elif isinstance(body, dict):
            out.extend(f"- **{k}**: {v}" for k, v in body.items())
        else:
            out.append(str(body))
        out.append("")
    if disclaimer:
        out.append("---")
        out.append(f"*{disclaimer}*")
    return "\n".join(out)
