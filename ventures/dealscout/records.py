"""Public-record ingestion.

Every county publishes distress signals somewhere: probate filings, tax-lien
sales, lis pendens / foreclosure notices, code-violation dockets.  Formats differ
per county, so DealScout uses one normalized row shape and one adapter per
source.  `from_csv` is the universal adapter (most counties export CSV or you
can get one from a records vendor); `from_url_json` shows the shape of a live
adapter for counties with an open-data API (Socrata/ArcGIS style).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

SIGNAL_TYPES = ("probate", "tax_lien", "pre_foreclosure", "code_violation", "vacant", "divorce")


@dataclass
class Record:
    signal: str                 # one of SIGNAL_TYPES
    parcel: str
    address: str
    city: str
    state: str
    zip: str
    owner: str
    owner_mailing: str          # where the tax bill goes; != address means absentee
    assessed_value: float
    filed: date
    amount: float = 0.0         # lien / arrears / judgment amount if any
    phone: Optional[str] = None
    notes: str = ""
    extra: dict = field(default_factory=dict)


def _f(x: str) -> float:
    try:
        return float(str(x).replace("$", "").replace(",", "") or 0)
    except ValueError:
        return 0.0


def from_rows(rows: list[dict]) -> list[Record]:
    out = []
    for r in rows:
        sig = (r.get("signal") or r.get("type") or "").strip().lower()
        if sig not in SIGNAL_TYPES:
            continue
        out.append(Record(
            signal=sig, parcel=r.get("parcel", ""), address=r.get("address", "").strip(),
            city=r.get("city", ""), state=r.get("state", ""), zip=str(r.get("zip", "")),
            owner=r.get("owner", "").strip(), owner_mailing=r.get("owner_mailing", "").strip(),
            assessed_value=_f(r.get("assessed_value", 0)), filed=date.fromisoformat(r["filed"][:10]),
            amount=_f(r.get("amount", 0)), phone=(r.get("phone") or None), notes=r.get("notes", ""),
        ))
    return out


def from_csv(text: str) -> list[Record]:
    return from_rows(list(csv.DictReader(io.StringIO(text))))


def from_url_json(url: str, mapping: dict[str, str], timeout: float = 20.0) -> list[Record]:
    """Live adapter: GET a JSON array and rename fields via `mapping` {ours: theirs}."""
    import httpx

    data = httpx.get(url, timeout=timeout).json()
    rows = data if isinstance(data, list) else data.get("results") or data.get("features") or []
    normalized = []
    for item in rows:
        item = item.get("attributes", item)  # ArcGIS wraps rows
        normalized.append({ours: item.get(theirs, "") for ours, theirs in mapping.items()})
    return from_rows(normalized)
