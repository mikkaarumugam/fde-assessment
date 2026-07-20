# Charity Growth Lookup

A tool for mhance's sales team to instantly see whether a UK charity is **growing
or shrinking** — replacing the manual, one-record-at-a-time checks on the Charity
Commission register.

Type a **charity name or registration number** and get back:

- **Smart name search** — a name like *cancer* returns a ranked shortlist to
  **pick from** (registration numbers go straight through); no more silently
  landing on the wrong charity
- **Income** over the last 3 years, with an **up / flat / down** trend indicator
- **Expenditure** over the same period, with its own trend indicator
- **Key people / trustees** (incl. who chairs the board and other charities they sit on)
- A **🔥 Hot prospect** flag when income jumped **more than 10% year-on-year**
- A grouped **income vs. expenditure bar chart**
- **CSV export** so the data drops straight into a spreadsheet

Data comes from the free [Charity Commission Register of Charities API](https://api-portal.charitycommission.gov.uk/).
All code lives in [`charity-tool/`](charity-tool/).

---

## Running it

**1. Get a free API key** — register at
<https://api-portal.charitycommission.gov.uk/>, subscribe to the *Register of
Charities* product, and copy your subscription key.

**2. Configure it**

```bash
cd charity-tool
cp .env.example .env          # then paste your key into .env
```

**3. Install and run**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://localhost:8000> and search — try `216401` (NSPCC) or a name like
`Oxfam`.

**Run the tests** (no network / key needed):

```bash
pytest
```

---

## How it works

```
Browser ── /api/charity?q=… ──> FastAPI ──> Charity Commission API
   ▲                               │  (cached, 24h TTL)
   └──── JSON / CSV ───────────────┘
```

All paths below are under `charity-tool/`:

- **`app/charity_client.py`** — calls the register endpoints, then normalises the
  (inconsistent) responses into one clean report, and ranks name-search results:
  - `searchCharityName/{name}` — resolves / lists candidates for a name
  - `charityfinancialhistory/{regno}/0` — yearly income & expenditure
  - `charitytrusteeinformation/{regno}/0` — trustees (note: the `charitytrustees`
    route in some docs 404s; this is the one that works)
  - `allcharitydetails/{regno}/0` — name, status, website, activities
- **`app/analysis.py`** — pure, unit-tested trend + hot-prospect logic.
- **`app/cache.py`** — in-memory TTL cache wrapping outbound calls.
- **`app/main.py`** — FastAPI routes (`/api/search`, `/api/charity`, `/api/charity.csv`) + static UI.
- **`static/`** — a single-page vanilla HTML/JS/CSS front end (no build step).
- **`tests/`** — 17 unit tests for the trend, hot-prospect, and search-ranking logic.

---

## Decisions made

- **FastAPI + vanilla JS, one process, no database.** Fastest path to a clean,
  demonstrable tool: typed JSON endpoints, a trivially added CSV route, and a
  static front end with zero build tooling. Nothing here needs a heavier stack.
- **Trend = first vs. last of the 3 years, with a ±2% dead-band.** Charity
  finances wobble year to year; without a dead-band a 0.5% drift reads as a
  "trend". 2% keeps "flat" honest. (Constant in `analysis.py`, easy to tune.)
- **Hot prospect = latest year income >10% above the *prior* year.** The brief's
  signal is year-on-year growth, so it looks at the two most recent years rather
  than the whole 3-year window — a charity that grew years ago but is flat now
  isn't a *current* prospect.
- **Disambiguation over guessing.** The register's name search returns matches
  alphabetically and in bulk (*cancer* → 1,200+), so silently taking the top hit
  lands on the wrong charity. Instead a name search returns a **candidate list**,
  ranked by relevance (exact → prefix → whole-word → substring) so the intended
  charity surfaces first; an exact/single match skips the picker. Broad one-word
  queries can't be income-ranked without fetching every match, so the UI shows
  "top N of M — refine to narrow" rather than pretending the list is complete.
- **24-hour cache.** Register financials update at most annually, so we don't need
  to hit the Charity Commission on every keystroke. In-memory keeps it dependency-
  free; for multi-process or persistent caching, swap `TTLCache` for
  `requests-cache`/SQLite or Redis — the client only depends on a `.get/.set`.
- **Defensive normalisation.** Endpoint field names/shapes were verified against
  the live API, but values can be `null` and one charity's trustees can be redacted
  — every section degrades gracefully ("Not published by the API") instead of
  erroring.
- **Secrets stay out of git.** The key lives in `.env` (gitignored); `.env.example`
  documents the variable. The app fails fast with a clear message if it's missing.

## Roadmap — where I'd take this next

The whole arc:
**standalone lookup → filtered segments → bulk prospecting → auto-sync into the CRM.**

### 1. Multi-charity search by sector, geography, and income band

Deliberately left out of v1, for a concrete reason. The register API **only
searches by name**, and even that is a literal text match — a search for
`education` returns 8,000+ charities with "education" *in their name*, not the
education *sector*. Every faceted endpoint I probed (`searchByClassification`,
`charitiesByArea`, …) returns 404. The sector (classification) and geography
(area of operation) data exists, but only **one charity at a time, by number** —
you can't query across the population. It's a lookup service, not a search engine.

To do it properly you stop asking the API to search and bring the whole dataset
somewhere you *can* query:

```
INGEST            →  STORE       →  QUERY        →  ENRICH          →  PRESENT
(nightly bulk        (SQLite /      (filter by      (reuse the         (reuse the table,
 register download)   Postgres)      sector/geo/     existing trend +    CSV, and detail
                                     income band)    hot-prospect        view already built)
                                                     logic)
```

The Charity Commission publishes the [full register as a bulk download](https://register-of-charities.charitycommission.gov.uk/en/register/full-register-download)
(CSV/JSON, refreshed daily) with linked tables for the charity record, financials,
area of operation, and classification. Load it into a database and sector /
geography / income become ordinary filters. Crucially, **the differentiated parts —
the trend/hot-prospect analysis and the UI/CSV — are already done**; this is mostly
a new data source behind the same tool.

- **Faster path:** [CharityBase](https://charitybase.uk/) has already ingested the
  register and exposes filters for cause/sector, location, and income — prototype
  on it to validate the sales workflow before building a pipeline.
- **Sequencing:** prototype on CharityBase; own the data (bulk extract → DB) if it
  becomes core, because owning it lets you **join against mhance's own CRM data**
  (who's already a customer / been contacted).
- **Decisions to make:** income-band buckets, sector taxonomy (the Commission's
  classification codes vs. a curated sales-friendly list), geography granularity
  (region vs. local authority), and refresh cadence.

### 2. Push hot prospects into Dynamics 365 (the sales team's CRM)

mhance is a Microsoft Dynamics 365 partner — their sales team lives in the CRM all
day. The insight should reach them *there*, not in a separate tool they have to
remember to open. So: a charity this tool flags as a **hot prospect** is created
automatically as a **Lead** in Dynamics, with the income trend attached, refreshed
overnight.

Dynamics CRM is built on **Dataverse**, which exposes a **Web API** — creating a
Lead is a standard authenticated request (or no-code via **Power Automate**). The
plumbing is trivial; the real work is **access and data model**: an admin
registering the app in Microsoft Entra ID, and mapping to *their* Lead schema and
duplicate rules. That's an environment/trust problem, not a coding one — which is
why it isn't faked here without their instance.

Combined with #1, this closes the loop: filter the whole register for growing
charities in a target segment, and drop them straight into the sales team's
pipeline.
