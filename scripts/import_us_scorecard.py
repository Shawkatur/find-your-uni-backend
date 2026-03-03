#!/usr/bin/env python3
"""
Import US College Scorecard data into universities table.
API docs: https://collegescorecard.ed.gov/data/documentation/
No API key required for basic fields; set SCORECARD_API_KEY in .env for higher rate limits.

Usage:
  python scripts/import_us_scorecard.py            # import up to 1000 schools
  python scripts/import_us_scorecard.py --limit 5000
  python scripts/import_us_scorecard.py --page 2   # pagination
"""
import argparse
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.db.client import get_client

SCORECARD_URL = "https://api.data.gov/ed/collegescorecard/v1/schools"

FIELDS = ",".join([
    "school.name",
    "school.city",
    "school.state",
    "school.school_url",
    "school.ownership",
    "2022.cost.tuition.out_of_state",
    "2022.cost.tuition.in_state",
    "2022.admissions.admission_rate.overall",
    "2022.student.size",
])


def _parse_school(item: dict) -> dict | None:
    school  = item.get("school", {})
    cost    = (item.get("2022") or {}).get("cost", {})
    admiss  = (item.get("2022") or {}).get("admissions", {})

    name = school.get("name", "").strip()
    city = school.get("city", "").strip()
    state = school.get("state", "").strip()

    if not name:
        return None

    tuition_out = cost.get("tuition", {}).get("out_of_state")
    tuition_in  = cost.get("tuition", {}).get("in_state")
    tuition     = tuition_out or tuition_in or 0

    admission_rate_raw = (admiss.get("admission_rate") or {}).get("overall")
    acceptance_rate = round(float(admission_rate_raw) * 100, 2) if admission_rate_raw else None

    return {
        "name":                 name,
        "country":              "US",
        "city":                 f"{city}, {state}".strip(", "),
        "tuition_usd_per_year": int(tuition),
        "acceptance_rate_overall": acceptance_rate,
        "website":              school.get("school_url"),
        "data_source":          "us_scorecard",
    }


async def run_sync(limit: int = 1000, page: int = 0, api_key: str | None = None) -> int:
    settings = get_settings()
    key = api_key or settings.SCORECARD_API_KEY or "DEMO_KEY"
    client = await get_client()

    params = {
        "api_key":      key,
        "fields":       FIELDS,
        "per_page":     100,
        "page":         page,
        "_sort":        "2022.student.size:desc",  # largest schools first
    }

    total_inserted = 0
    pages_needed   = (limit + 99) // 100

    async with httpx.AsyncClient(timeout=30) as http:
        for p in range(pages_needed):
            params["page"] = page + p
            resp = await http.get(SCORECARD_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", [])
            if not results:
                print(f"  No more results at page {params['page']}")
                break

            batch = [r for item in results if (r := _parse_school(item)) is not None]

            if batch:
                res = await client.table("universities").upsert(
                    batch,
                    on_conflict="name,country",
                    ignore_duplicates=False,
                ).execute()
                inserted = len(res.data or [])
                total_inserted += inserted
                print(f"  Page {params['page']}: {inserted} rows upserted")

    print(f"Total upserted: {total_inserted}")
    return total_inserted


def main():
    parser = argparse.ArgumentParser(description="Sync US College Scorecard → Supabase")
    parser.add_argument("--limit", type=int, default=1000, help="Max schools to import")
    parser.add_argument("--page",  type=int, default=0,    help="Start page (0-based)")
    args = parser.parse_args()

    asyncio.run(run_sync(limit=args.limit, page=args.page))


if __name__ == "__main__":
    main()
