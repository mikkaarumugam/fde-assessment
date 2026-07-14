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

## Not built (and how I'd extend it)

The stretch goal of **searching by geography / sector / income band across many
charities at once** isn't included: the per-charity register API isn't built for
that kind of filtered bulk query. The right approach is to load the Charity
Commission's [full register download](https://register-of-charities.charitycommission.gov.uk/en/full-register-download)
(or the CharityBase / findthatcharity mirrors, which already index those facets)
into a local table and query that, then reuse this same analysis + UI layer to
render the multi-charity results.
