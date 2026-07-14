"""FastAPI app: serves the UI and the JSON / CSV charity-lookup endpoints."""

from __future__ import annotations

import csv
import io
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .cache import TTLCache
from .charity_client import (
    CharityClient,
    CharityNotFound,
    CharityToolError,
    MissingAPIKey,
)

load_dotenv()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Charity Growth Lookup", version="1.0")

# One shared client + cache for the process lifetime.
_cache = TTLCache(ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "86400")))
client = CharityClient(cache=_cache)

# Human-friendly labels for trends, reused by JSON + CSV.
TREND_WORDS = {"up": "Up", "flat": "Flat", "down": "Down", "unknown": "N/A"}


def _error_response(exc: CharityToolError) -> JSONResponse:
    """Map our exception types to sensible HTTP statuses + clean messages."""
    if isinstance(exc, MissingAPIKey):
        status = 500
    elif isinstance(exc, CharityNotFound):
        status = 404
    else:  # CharityAPIError and any other CharityToolError
        status = 502
    return JSONResponse(status_code=status, content={"error": str(exc)})


@app.get("/api/search")
def search_charities(q: str = Query(..., description="Charity name to search for")):
    """Return candidate charities so the user can disambiguate a name search."""
    try:
        data = client.search(q)
        return {
            "query": q,
            "count": len(data["results"]),
            "total": data["total"],
            "results": data["results"],
        }
    except CharityToolError as exc:
        return _error_response(exc)


@app.get("/api/charity")
def get_charity(q: str = Query(..., description="Charity name or registration number")):
    try:
        return client.build_report(q)
    except CharityToolError as exc:
        return _error_response(exc)


@app.get("/api/charity.csv")
def get_charity_csv(q: str = Query(...)):
    try:
        report = client.build_report(q)
    except CharityToolError as exc:
        return _error_response(exc)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Charity name", report["charity_name"]])
    writer.writerow(["Registration number", report["reg_charity_number"]])
    writer.writerow(["Status", report["reg_status"]])
    writer.writerow(
        ["Hot prospect", "Yes" if report["hot_prospect"] else "No",
         _fmt_pct(report["hot_prospect_change"])]
    )
    writer.writerow([])
    writer.writerow(["Financial year", "Income (GBP)", "Expenditure (GBP)"])
    for row in report["financials"]:
        writer.writerow([row["label"], _num(row["income"]), _num(row["expenditure"])])
    writer.writerow([])
    writer.writerow([
        "Income trend", TREND_WORDS[report["income_trend"]],
        _fmt_pct(report["income_change"]),
    ])
    writer.writerow([
        "Expenditure trend", TREND_WORDS[report["expenditure_trend"]],
        _fmt_pct(report["expenditure_change"]),
    ])

    filename = f"charity_{report['reg_charity_number']}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


# Serve JS/CSS. Mounted last so it doesn't shadow the API routes above.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _num(value):
    return "" if value is None else int(value)


def _fmt_pct(change):
    return "" if change is None else f"{change * 100:+.1f}%"
