"""Client for the Charity Commission 'Register of Charities' API.

Wraps the handful of endpoints we need, normalises their (slightly messy)
responses into one clean report, and caches raw responses via TTLCache.

Endpoint shapes were verified live against the API before writing this.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

from .analysis import last_n_years, summarise_financials
from .cache import TTLCache

BASE_URL = "https://api.charitycommission.gov.uk/register/api"


class CharityToolError(Exception):
    """Base class so callers can catch everything we raise."""


class MissingAPIKey(CharityToolError):
    pass


class CharityNotFound(CharityToolError):
    pass


class CharityAPIError(CharityToolError):
    """The upstream API failed or returned something unusable."""


class CharityClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        cache: Optional[TTLCache] = None,
        timeout: float = 25.0,
    ) -> None:
        self.api_key = api_key or os.getenv("CHARITY_COMMISSION_API_KEY")
        self.cache = cache if cache is not None else TTLCache()
        self.timeout = timeout

    # ---- low-level HTTP -------------------------------------------------

    def _get(self, path: str):
        """GET {BASE_URL}/{path}, cached. Returns parsed JSON (list or dict)."""
        if not self.api_key:
            raise MissingAPIKey(
                "No API key configured. Copy .env.example to .env and set "
                "CHARITY_COMMISSION_API_KEY."
            )

        cached = self.cache.get(path)
        if cached is not None:
            return cached

        url = f"{BASE_URL}/{path}"
        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Cache-Control": "no-cache",
        }
        try:
            resp = httpx.get(url, headers=headers, timeout=self.timeout)
        except httpx.RequestError as exc:
            raise CharityAPIError(f"Could not reach the Charity Commission API: {exc}")

        if resp.status_code == 404:
            # Signal "no such resource" distinctly from a hard failure.
            return None
        if resp.status_code == 401 or resp.status_code == 403:
            raise CharityAPIError(
                "Charity Commission API rejected the key (401/403). Check "
                "CHARITY_COMMISSION_API_KEY and that your subscription is active."
            )
        if resp.status_code >= 400:
            raise CharityAPIError(
                f"Charity Commission API returned {resp.status_code} for /{path}."
            )

        try:
            data = resp.json()
        except ValueError:
            raise CharityAPIError("Charity Commission API returned invalid JSON.")

        self.cache.set(path, data)
        return data

    # ---- endpoint wrappers ---------------------------------------------

    def search_by_name(self, name: str) -> list[dict]:
        data = self._get(f"searchCharityName/{name}")
        return data if isinstance(data, list) else []

    def financial_history(self, regno: int, sub: int = 0) -> list[dict]:
        data = self._get(f"charityfinancialhistory/{regno}/{sub}")
        return data if isinstance(data, list) else []

    def trustees(self, regno: int, sub: int = 0) -> list[dict]:
        data = self._get(f"charitytrusteeinformation/{regno}/{sub}")
        return data if isinstance(data, list) else []

    def details(self, regno: int, sub: int = 0) -> Optional[dict]:
        data = self._get(f"allcharitydetails/{regno}/{sub}")
        return data if isinstance(data, dict) else None

    # ---- resolution + report -------------------------------------------

    def search(self, query: str, limit: int = 10) -> dict:
        """Rank candidate charities for a name search.

        The API returns matches alphabetically (a search for 'cancer' returns
        1200+, so the big names would never make the first page). We prefer
        active main charities, de-dupe by number, then rank by name relevance so
        the charity the user most likely meant surfaces first. Returns the top
        `limit` plus the total match count so the UI can prompt a refine.
        """
        query = (query or "").strip()
        if not query:
            return {"results": [], "total": 0}
        q = query.lower()

        matches = self.search_by_name(query)
        active_main = [
            m
            for m in matches
            if m.get("reg_status") == "R"
            and not m.get("date_of_removal")
            and (m.get("group_subsid_suffix") in (0, None))
        ]
        pool = active_main or matches

        seen: set[int] = set()
        unique = []
        for m in pool:
            regno = m.get("reg_charity_number")
            if regno is None or regno in seen:
                continue
            seen.add(regno)
            unique.append(m)

        unique.sort(key=lambda m: _relevance(m.get("charity_name") or "", q))

        results = [
            {
                "reg_charity_number": m.get("reg_charity_number"),
                "charity_name": m.get("charity_name"),
                "reg_status": _status_label(m.get("reg_status")),
                "registered_year": (m.get("date_of_registration") or "")[:4] or None,
            }
            for m in unique[:limit]
        ]
        return {"results": results, "total": len(unique)}

    def resolve(self, query: str) -> int:
        """Turn a user's input (reg number or name) into a registered number."""
        query = (query or "").strip()
        if not query:
            raise CharityNotFound("Please enter a charity name or registration number.")

        if query.isdigit():
            return int(query)

        candidates = self.search(query, limit=1)["results"]
        if not candidates:
            raise CharityNotFound(f"No charity found matching '{query}'.")
        return int(candidates[0]["reg_charity_number"])

    def build_report(self, query: str) -> dict:
        """The one call the API layer needs: resolve + fetch + analyse."""
        regno = self.resolve(query)

        details = self.details(regno) or {}
        history = self.financial_history(regno)
        if not details and not history:
            raise CharityNotFound(
                f"No charity found for registration number {regno}."
            )

        rows = last_n_years(history, n=3)
        summary = summarise_financials(rows)
        trustees = self._normalise_trustees(regno, details)
        activities = self._activities(details)

        return {
            "reg_charity_number": regno,
            "charity_name": details.get("charity_name") or f"Charity {regno}",
            "reg_status": _status_label(details.get("reg_status")),
            "website": _normalise_url(details.get("web")),
            "activities": activities,
            "latest_income": details.get("latest_income"),
            "latest_expenditure": details.get("latest_expenditure"),
            "financials": rows,
            **summary,
            "trustees": trustees,
        }

    # ---- normalisation helpers -----------------------------------------

    def _normalise_trustees(self, regno: int, details: dict) -> list[dict]:
        """Prefer the rich trustee endpoint; fall back to names in details."""
        raw = self.trustees(regno)
        if raw:
            return [
                {
                    "name": t.get("name"),
                    "is_chair": bool(t.get("is_chair")),
                    "appointed": (t.get("date_of_appointment") or "")[:10] or None,
                    "also_trustee_of": t.get("charity_name"),
                }
                for t in raw
                if t.get("name")
            ]
        # Fallback: allcharitydetails carries a plain trustee_names list.
        return [
            {"name": t.get("trustee_name"), "is_chair": False,
             "appointed": None, "also_trustee_of": None}
            for t in (details.get("trustee_names") or [])
            if t.get("trustee_name")
        ]

    @staticmethod
    def _activities(details: dict) -> list[str]:
        """Pull the 'What' classifications as a short activity list."""
        out = []
        for c in details.get("who_what_where") or []:
            if c.get("classification_type") == "What" and c.get("classification_desc"):
                out.append(c["classification_desc"])
        return out


def _relevance(name: str, q: str) -> tuple:
    """Sort key (lower is better) ranking a charity name against the query.

    Exact match first, then names starting with the query, then a whole-word
    match, then any substring by position. Ties break by length then alphabet
    so shorter, cleaner names win.
    """
    n = name.lower()
    if n == q:
        return (0, 0, n)
    if n.startswith(q):
        return (1, len(n), n)
    if q in n.split():
        return (2, n.find(q), n)
    idx = n.find(q)
    return (3, idx if idx >= 0 else 10**6, n)


def _status_label(code: Optional[str]) -> str:
    return {
        "R": "Registered",
        "RM": "Removed",
    }.get((code or "").upper(), code or "Unknown")


def _normalise_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        return "https://" + url
    return url
