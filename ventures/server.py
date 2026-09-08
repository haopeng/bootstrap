"""One FastAPI app that serves every product: a landing page per product with
pricing, an upload/paste form, and a JSON API.  Styled with the Bootstrap CSS
that lives in this very repository."""
from __future__ import annotations

import json
import os
from datetime import date, datetime

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from ventures.core import PRICING, Store, get_llm
from ventures.core.billing import checkout_url

HERE = os.path.dirname(__file__)
REPO = os.path.dirname(HERE)
app = FastAPI(title="ventures", version="0.1.0")
app.mount("/assets", StaticFiles(directory=os.path.join(REPO, "docs", "assets")), name="assets")

PRODUCTS = {
    "taxguard": ("TaxGuard", "Contract & 1099 review for small businesses", "Upload contracts and invoices; get flagged clauses, 1099 exposure and a filing checklist."),
    "dealscout": ("DealScout", "Distressed-property leads, done by the book", "Public-record leads ranked by motivation, owner letters, deal memos. Consent-gated outreach."),
    "launchradar": ("LaunchRadar", "Find the conversations your product belongs in", "HN + Reddit monitoring, relevance scoring, honest reply drafts. You post; we never do."),
    "dunning": ("Dunning", "Polite invoice follow-up on autopilot", "4-step reminders in your customer's business hours. Stops on disputes. Never a collector."),
    "reviewreply": ("ReviewReply", "Answer every review in your voice", "Drafted replies to Google/Yelp reviews + a weekly sentiment digest for local businesses."),
    "bidscout": ("BidScout", "Government bids matched to your shop", "SAM.gov and state portals screened against your NAICS, certs and area. Go/no-go memos + calendar."),
    "leasecheck": ("LeaseCheck", "Read your lease before you sign it", "Red flags in plain English, your state's rules, and a negotiation email. $19."),
}


def page(title: str, body: str) -> HTMLResponse:
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>
<link rel="stylesheet" href="/assets/css/bootstrap.css"><style>body{{padding-top:60px}} pre{{white-space:pre-wrap}}</style></head>
<body><div class="navbar navbar-fixed-top"><div class="navbar-inner"><div class="container">
<a class="brand" href="/">ventures</a><ul class="nav">{''.join(f'<li><a href="/{k}">{v[0]}</a></li>' for k, v in PRODUCTS.items())}</ul>
</div></div></div><div class="container">{body}</div></body></html>"""
    return HTMLResponse(html)


@app.get("/", response_class=HTMLResponse)
def index():
    cards = "".join(
        f'<div class="span4"><h3>{n}</h3><p><strong>{t}</strong></p><p>{d}</p>'
        f'<p><a class="btn btn-primary" href="/{k}">Try {n} »</a></p></div>'
        for k, (n, t, d) in PRODUCTS.items())
    mode = "live (Claude)" if get_llm().available else "rules-only demo (set ANTHROPIC_API_KEY for the full product)"
    return page("ventures", f'<div class="hero-unit"><h1>Seven small AI businesses</h1><p>Each one does a job a small business '
                f'pays for today, legitimately. Mode: {mode}.</p></div><div class="row">{cards}</div>')


def _pricing(k: str) -> str:
    rows = "".join(f"<tr><td>{p.name}</td><td>${p.price_usd:g} {p.unit}</td><td>{p.included}</td>"
                   f'<td><a class="btn btn-success" href="{checkout_url(p)}">Buy</a></td></tr>' for p in PRICING[k])
    return f'<h3>Pricing</h3><table class="table table-striped"><tbody>{rows}</tbody></table>'


FORMS = {
    "taxguard": '<form method="post" action="/api/taxguard" enctype="multipart/form-data"><input type="file" name="files" multiple> <button class="btn btn-primary">Review</button></form>',
    "dealscout": '<form method="post" action="/api/dealscout" enctype="multipart/form-data"><input type="file" name="csv"> <input name="company" placeholder="Your company"> <input name="sender" placeholder="Your name"> <input name="phone" placeholder="Phone"> <button class="btn btn-primary">Scan</button></form>',
    "launchradar": '<form method="post" action="/api/launchradar"><input name="product" placeholder="Product name"><br><textarea name="description" rows="4" cols="80" placeholder="What it does, who it is for, what pain it removes"></textarea><br><label><input type="checkbox" name="live" value="1"> Search HN + Reddit live</label> <button class="btn btn-primary">Scan</button></form>',
    "dunning": '<form method="post" action="/api/dunning" enctype="multipart/form-data"><input type="file" name="csv"> <input name="sender" placeholder="Signature, e.g. Sam at Ortiz Studio"> <button class="btn btn-primary">Run today</button></form><p><small>CSV columns: id,customer,email,amount,due,pay_url,late_fee_allowed,late_fee_pct</small></p>',
    "reviewreply": '<form method="post" action="/api/reviewreply" enctype="multipart/form-data"><input type="file" name="json"> <input name="business" placeholder="Business"> <input name="owner" placeholder="Owner first name"> <input name="contact" placeholder="Contact email/phone"> <button class="btn btn-primary">Draft replies</button></form>',
    "bidscout": '<form method="post" action="/api/bidscout" enctype="multipart/form-data"><input type="file" name="json"> <input name="company" placeholder="Company"> <input name="naics" placeholder="NAICS, comma separated"> <input name="keywords" placeholder="keywords"> <input name="states" placeholder="TX,OK"> <input name="certs" placeholder="SB,SDVOSB"> <button class="btn btn-primary">Screen</button></form>',
    "leasecheck": '<form method="post" action="/api/leasecheck"><textarea name="text" rows="10" cols="90" placeholder="Paste your lease"></textarea><br><input name="state" placeholder="State (TX)"> <button class="btn btn-primary">Check my lease</button></form>',
}


@app.get("/checkout/{product}/{plan}", response_class=HTMLResponse)
def checkout_stub(product: str, plan: str):
    return page("Checkout", f"<h2>Checkout: {product} / {plan}</h2><p>Set <code>STRIPE_SECRET_KEY</code> to turn this into a real Stripe Checkout session.</p>")


def _md(md: str, extra: dict | None = None):
    return PlainTextResponse(md, headers={"X-Result": json.dumps(extra or {})[:900]})


@app.post("/api/taxguard")
async def api_taxguard(files: list[UploadFile] = File(...)):
    from ventures.taxguard import review
    from ventures.taxguard.ingest import load_bytes
    docs = [load_bytes(f.filename, await f.read()) for f in files]
    r = review(docs, Store())
    return _md(r["report_md"], {"job_id": r["job_id"], "findings": len(r["findings"])})


@app.post("/api/dealscout")
async def api_dealscout(csv: UploadFile = File(...), company: str = Form(...), sender: str = Form(...), phone: str = Form(...)):
    from ventures.dealscout import run
    from ventures.dealscout.records import from_csv
    r = run(from_csv((await csv.read()).decode()), sender, company, phone, store=Store())
    return _md(r["report_md"], {"job_id": r["job_id"], "leads": len(r["leads"])})


@app.post("/api/launchradar")
async def api_launchradar(product: str = Form(...), description: str = Form(...), live: str = Form("")):
    from ventures.launchradar import scan
    r = scan(product, description, threads=None if live else [], live=bool(live), store=Store())
    return _md(r["report_md"], {"job_id": r["job_id"], "drafts": len(r["queue"])})


@app.post("/api/dunning")
async def api_dunning(csv: UploadFile = File(...), sender: str = Form(...)):
    import csv as _csv, io
    from ventures.dunning import run_day
    from ventures.dunning.engine import Invoice
    rows = _csv.DictReader(io.StringIO((await csv.read()).decode()))
    invs = [Invoice(r["id"], r["customer"], r["email"], float(r["amount"]), date.fromisoformat(r["due"]), pay_url=r.get("pay_url", ""),
                    late_fee_allowed=r.get("late_fee_allowed", "").lower() in ("1", "true", "yes"), late_fee_pct=float(r.get("late_fee_pct") or 0))
            for r in rows]
    r = run_day(invs, sender, store=Store())
    return _md(r["report_md"], {"job_id": r["job_id"], "sent": len(r["sent"])})


@app.post("/api/reviewreply")
async def api_reviewreply(json_file: UploadFile = File(..., alias="json"), business: str = Form(...), owner: str = Form(...), contact: str = Form(...)):
    from ventures.reviewreply import run
    r = run(json.loads(await json_file.read()), business, owner, contact, Store())
    return _md(r["report_md"], {"job_id": r["job_id"], "drafts": len(r["drafts"])})


@app.post("/api/bidscout")
async def api_bidscout(json_file: UploadFile = File(..., alias="json"), company: str = Form(...), naics: str = Form(""),
                       keywords: str = Form(""), states: str = Form(""), certs: str = Form("")):
    from ventures.bidscout import run
    from ventures.bidscout.engine import Profile
    split = lambda s: [x.strip() for x in s.split(",") if x.strip()]
    r = run(Profile(company, split(naics), split(keywords), split(states), split(certs)), json.loads(await json_file.read()), store=Store())
    return _md(r["report_md"], {"job_id": r["job_id"], "shortlist": len(r["shortlist"])})


@app.post("/api/leasecheck")
async def api_leasecheck(text: str = Form(...), state: str = Form("")):
    from ventures.leasecheck import review
    r = review(text, state, store=Store())
    return _md(r["report_md"], {"job_id": r["job_id"], "findings": len(r["findings"])})


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str):
    job = Store().get(job_id)
    return JSONResponse(job or {"error": "not found"}, status_code=200 if job else 404)


@app.get("/healthz")
def healthz():
    return {"ok": True, "llm": get_llm().available}


# Catch-all product page: registered last so fixed routes (/healthz, /checkout, /api) win.
@app.get("/{product}", response_class=HTMLResponse)
def product_page(product: str):
    if product not in PRODUCTS:
        return page("404", "<h1>Not found</h1>")
    n, t, d = PRODUCTS[product]
    return page(n, f"<h1>{n}</h1><p class='lead'>{t}</p><p>{d}</p>{FORMS[product]}{_pricing(product)}")
