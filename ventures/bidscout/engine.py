from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Profile:
    company: str
    naics: list[str]
    keywords: list[str]
    states: list[str]
    certifications: list[str] = field(default_factory=list)  # e.g. "SDVOSB", "WOSB", "8(a)", "HUBZone", "SB"
    max_value: float = 2_000_000
    min_days_to_respond: int = 7


SET_ASIDE_MAP = {
    "SB": ("small business", "total small business"), "WOSB": ("women", "wosb"), "SDVOSB": ("service-disabled", "sdvosb"),
    "8(a)": ("8(a)",), "HUBZone": ("hubzone",),
}


def match(profile: Profile, opp: dict, today: date) -> dict:
    reasons, score = [], 0.0
    if opp["naics"] and opp["naics"][:4] in {n[:4] for n in profile.naics}:
        score += 40; reasons.append(f"NAICS {opp['naics']} matches")
    kw = [k for k in profile.keywords if k.lower() in f"{opp['title']} {opp['description']}".lower()]
    if kw:
        score += min(10 * len(kw), 30); reasons.append("keywords: " + ", ".join(kw))
    if not opp["state"] or opp["state"] in profile.states:
        score += 10; reasons.append("place of performance OK")
    else:
        score -= 25; reasons.append(f"out of area ({opp['state']})")
    sa = opp["set_aside"].lower()
    if sa:
        eligible = [c for c in profile.certifications if any(w in sa for w in SET_ASIDE_MAP.get(c, (c.lower(),)))]
        if eligible:
            score += 20; reasons.append(f"set-aside matches your {eligible[0]}")
        else:
            score -= 30; reasons.append(f"set-aside '{opp['set_aside']}' — not eligible")
    days_left = (date.fromisoformat(opp["deadline"]) - today).days if opp["deadline"] else None
    if days_left is not None:
        if days_left < 0:
            score = 0; reasons.append("deadline passed")
        elif days_left < profile.min_days_to_respond:
            score -= 15; reasons.append(f"only {days_left} days to respond")
        else:
            reasons.append(f"{days_left} days to respond")
    if opp["value_estimate"] and opp["value_estimate"] > profile.max_value:
        score -= 20; reasons.append("above your max contract size")
    go = "GO" if score >= 60 else "MAYBE" if score >= 35 else "NO-GO"
    return {**opp, "score": round(max(score, 0)), "decision": go, "reasons": reasons, "days_left": days_left}


def ics(opps: list[dict], company: str) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:-//BidScout//{company}//EN"]
    for o in opps:
        if not o["deadline"]:
            continue
        d = o["deadline"].replace("-", "")
        lines += ["BEGIN:VEVENT", f"UID:{o['id']}@bidscout", f"DTSTART;VALUE=DATE:{d}", f"DTEND;VALUE=DATE:{d}",
                  f"SUMMARY:[{o['decision']}] Bid due: {o['title'][:60]}", f"DESCRIPTION:{o['url']}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
