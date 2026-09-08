# ventures — seven small AI businesses, built to be run

> 中文速览：这是对小红书那篇「美国草根用 AI 闷声发大财」四个故事的**合法复刻**，外加三个同模式的新点子。
> 每个产品都是可跑通的 Python 包：规则层永远可用，接上 Anthropic key 后 Claude 层自动增强。
> `python -m ventures demo` 一键跑全部七个；`python -m ventures serve` 起网站。原文里踩线的部分
> （AI 冒充真人打电话、论坛里伪装成路人打广告、第三方催收）都换成了同样赚钱但不违规的做法。

Every product here has the same shape and the same rule: **the rules layer always
runs; Claude makes it better when a key is present.** That keeps demos and tests
deterministic and means a customer never gets a blank report because of a rate limit.

```
python -m pip install -r ventures/requirements.txt
python -m ventures demo          # runs all 7 on sample data -> ventures/out/*.md
python -m ventures serve 8000    # landing pages + JSON API, styled with this repo's Bootstrap CSS
python -m pytest ventures/tests  # 14 tests, no network needed
export ANTHROPIC_API_KEY=...     # (or `ant auth login`) to switch every product to Claude
```

## The four stories, and what changed

| # | Article's version | What was wrong with it | What's built here |
|---|---|---|---|
| 1 | Upload contracts + invoices, AI finds risky clauses and compliance issues, generates filing docs. $42k/mo. | Nothing, as long as it doesn't pretend to be a CPA. | **TaxGuard** — regex rules for 12 clause types, 1099-NEC/K thresholds (2026 figures), vendor spend tracker, filing checklist, Claude-drafted redline email. |
| 2 | Bot scrapes county records, finds distressed owners, an ElevenLabs voice calls them and "they can't tell it's AI". | AI-voice calls without consent are TCPA robocalls (FCC, Feb 2024); several states require AI disclosure; no DNC scrub = fines per call. | **DealScout** — same public-record lead engine (probate, tax lien, pre-foreclosure, code violations, vacancy), motivation scoring, 70%-rule deal math, buyer memos. Direct mail always; SMS/voice only through a consent + DNC + quiet-hours gate, and every script says "I'm an AI". |
| 3 | AI finds people complaining on Reddit/HN and posts replies that "don't look like ads". $500k ARR. | That is astroturfing: against Reddit/HN rules, FTC endorsement guides, and it gets accounts banned. | **LaunchRadar** — same monitoring (HN Algolia + Reddit JSON), same relevance scoring, drafts a genuinely helpful reply that says "I built this", and puts it in an approval queue. It cannot post. |
| 4 | "AI debt collector", $400k/mo. | Third-party collection is FDCPA/Reg F territory with state licensing. | **Dunning** — first-party invoice follow-up for a business's own customers: 4-step sequence, customer business hours, late fee only if the contract allows, stops on dispute/"stop", hands off at 30 days. Banned-phrase check on every message. |

## Three new ideas found by the same pattern

The pattern behind all four stories: *a small business already pays a human by the hour to read
something boring; sell them the reading for a flat fee.* Three more places that pattern holds:

| Product | Who pays | Why now | Price |
|---|---|---|---|
| **ReviewReply** | Restaurants, clinics, salons, auto shops | Answering every review lifts local-search rank; owners never find the time. Never argues, never leaks private info (HIPAA-safe template). | $19/mo/location |
| **BidScout** | Landscapers, janitorial, IT, construction subs | SAM.gov + state portals publish set-aside bids nobody reads. Matches NAICS/certs/area, writes a go/no-go memo, emits an `.ics` deadline calendar. | $79/mo |
| **LeaseCheck** | Renters with 48 hours to sign | Consumer twin of TaxGuard. 11 red-flag rules, state notes (CA/TX/NY/WA/IL/FL), negotiation email. | $19/lease |

## Unit economics (checked by `test_pricing_margins`)

| Product | Price | Est. model cost / unit | Gross margin | Path to $10k/mo |
|---|---|---|---|---|
| TaxGuard | $49/doc, $199/mo | $0.60 / $20 | >90% | 50 bookkeeper subs |
| DealScout | $149/mo + $2,500/close | $6 | 96% | 20 wholesalers, or 4 closes |
| LaunchRadar | $29 / $99 mo | $4 / $15 | 85% | 350 indie subs |
| Dunning | $39/mo or 2% recovered | $3 | 92% | 250 subs, or $500k recovered |
| ReviewReply | $19/mo | $1.50 | 92% | 525 locations |
| BidScout | $79/mo | $6 | 92% | 125 contractors |
| LeaseCheck | $19/lease | $0.40 | 98% | 525 leases |

Model costs assume `claude-opus-5` list price with prompt caching on the system prompt.
`core/llm.py` is the only place the model is named.

## Go-to-market, in the order to try

1. **LeaseCheck and TaxGuard first.** Pay-per-use, no onboarding, buyer already searching ("is this lease clause legal", "do I need to send a 1099"). Content + one landing page each.
2. **Dunning second.** Distribution is free: LaunchRadar's own sample data is Dunning threads. Post honest replies by hand.
3. **DealScout and BidScout** sell into communities that already pay for data (wholesaler Facebook groups, contractor associations). Success-fee pricing removes the objection.
4. **ReviewReply** is a door-to-door product: walk into a business with their last five reviews already answered.

## Layout

```
ventures/
  core/          llm.py (Claude wrapper, NullLLM fallback), store.py (sqlite), billing.py (plans, Stripe stub), report.py
  taxguard/      ingest.py  engine.py  llm.py  pipeline.py
  dealscout/     records.py engine.py  compliance.py  outreach.py  llm.py  pipeline.py
  launchradar/   sources.py engine.py  llm.py  pipeline.py
  dunning/       engine.py  messages.py  pipeline.py
  reviewreply/   engine.py  pipeline.py
  bidscout/      sources.py engine.py  pipeline.py
  leasecheck/    engine.py  pipeline.py
  samples/       realistic input for every product
  tests/         product tests + stubbed-SDK tests for the Claude layer
  demo.py  server.py  __main__.py
```

## What is a stub and what is real

Real: every rules engine, scoring model, sequence, compliance gate, report, the Claude
integration (structured outputs, adaptive thinking, prompt caching, server-side refusal
fallback), the sqlite job store, the FastAPI app, the tests.

Stubbed (each is one API call away and marked in code): sending mail/SMS/voice (Lob, Twilio,
ElevenLabs), sending email (Postmark/SES), Stripe Checkout (works once `STRIPE_SECRET_KEY` is
set), live HN/Reddit/SAM.gov fetches (implemented, but this sandbox blocks outbound requests so
the demo uses fixtures), National DNC scrubbing (needs a SAN subscription).

## Legal lines this code will not cross

- No AI voice or text to a phone without documented prior express consent and a DNC scrub.
- No posting to forums on a user's behalf; every draft discloses the relationship.
- No third-party debt collection, no threats, no legal/credit language in reminders.
- No legal, tax or medical advice: every report carries a disclaimer and points to a professional.
