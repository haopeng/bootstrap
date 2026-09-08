"""SAM.gov opportunities API adapter (v2).  Requires a free api key from sam.gov;
returns [] on any failure so the pipeline can run on fixtures."""
from __future__ import annotations

import json
import os
from datetime import date


def sam_search(posted_from: date, posted_to: date, naics: list[str] = (), keyword: str = "", limit: int = 100) -> list[dict]:
    key = os.environ.get("SAM_API_KEY")
    if not key:
        return []
    import httpx

    params = {"api_key": key, "limit": limit, "postedFrom": posted_from.strftime("%m/%d/%Y"),
              "postedTo": posted_to.strftime("%m/%d/%Y"), "ptype": "o,k,p"}  # solicitation, combined synopsis, presolicitation
    if naics:
        params["ncode"] = ",".join(naics)
    if keyword:
        params["q"] = keyword
    try:
        r = httpx.get("https://api.sam.gov/opportunities/v2/search", params=params, timeout=30)
        r.raise_for_status()
        return [normalize(o) for o in r.json().get("opportunitiesData", [])]
    except Exception:
        return []


def normalize(o: dict) -> dict:
    return {
        "id": o.get("noticeId"), "title": o.get("title", ""), "agency": o.get("fullParentPathName", ""),
        "naics": str(o.get("naicsCode", "")), "set_aside": o.get("typeOfSetAsideDescription") or "",
        "posted": (o.get("postedDate") or "")[:10], "deadline": (o.get("responseDeadLine") or "")[:10],
        "state": (o.get("placeOfPerformance") or {}).get("state", {}).get("code", ""),
        "description": o.get("description", "") or "", "url": o.get("uiLink", ""),
        "value_estimate": float(o.get("award", {}).get("amount", 0) or 0),
    }


def from_fixture(path: str) -> list[dict]:
    with open(path) as f:
        return json.load(f)
