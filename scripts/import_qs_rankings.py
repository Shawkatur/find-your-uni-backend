#!/usr/bin/env python3
"""
Import QS World University Rankings from a Kaggle CSV.

Usage:
  # First-time seed
  python scripts/import_qs_rankings.py --file qs_rankings_2024.csv

  # Update existing rows (upsert)
  python scripts/import_qs_rankings.py --file qs_rankings_2025.csv --update

Download the dataset from:
  https://www.kaggle.com/datasets/darrylljk/worlds-best-universities-qs-rankings
  CSV columns expected: Institution, Country, Overall Score, Rank, ...
"""
import argparse
import asyncio
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.db.client import get_client


# Map known QS country names → ISO 3166-1 alpha-2
COUNTRY_MAP = {
    "United States": "US",
    "United Kingdom": "GB",
    "Australia": "AU",
    "Canada": "CA",
    "Germany": "DE",
    "France": "FR",
    "Japan": "JP",
    "China (Mainland)": "CN",
    "South Korea": "KR",
    "Netherlands": "NL",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Singapore": "SG",
    "Hong Kong SAR": "HK",
    "New Zealand": "NZ",
    "Malaysia": "MY",
    "India": "IN",
    "Bangladesh": "BD",
    "Denmark": "DK",
    "Finland": "FI",
    "Norway": "NO",
    "Belgium": "BE",
    "Austria": "AT",
    "Italy": "IT",
    "Spain": "ES",
    "Russia": "RU",
    "Brazil": "BR",
    "Mexico": "MX",
    "Argentina": "AR",
    "South Africa": "ZA",
    "Ireland": "IE",
    "Portugal": "PT",
    "Czech Republic": "CZ",
    "Poland": "PL",
    "Turkey": "TR",
    "Thailand": "TH",
    "Indonesia": "ID",
    "Pakistan": "PK",
    "Saudi Arabia": "SA",
    "United Arab Emirates": "AE",
    "Egypt": "EG",
    "Nigeria": "NG",
    "Kenya": "KE",
    "Ghana": "GH",
}

# Possible column name variants in different Kaggle CSV versions
COL_ALIASES = {
    "institution": ["Institution", "university_name", "University", "Name", "name"],
    "country":     ["Country", "country", "Location"],
    "rank":        ["Rank", "rank", "2024 QS World University Rankings", "QS Rank"],
    "score":       ["Overall Score", "Score", "overall_score"],
}


def _find_col(df: pd.DataFrame, aliases: list[str]) -> str | None:
    for alias in aliases:
        if alias in df.columns:
            return alias
    return None


def _parse_rank(val) -> int | None:
    if pd.isna(val):
        return None
    s = str(val).strip()
    # Handle ranges like "501-510" → take lower bound
    m = re.match(r"(\d+)", s)
    return int(m.group(1)) if m else None


def _iso2(country_raw: str) -> str:
    return COUNTRY_MAP.get(country_raw.strip(), country_raw[:2].upper())


async def import_rankings(csv_path: str, update: bool = False) -> int:
    client = await get_client()
    df = pd.read_csv(csv_path)

    inst_col    = _find_col(df, COL_ALIASES["institution"])
    country_col = _find_col(df, COL_ALIASES["country"])
    rank_col    = _find_col(df, COL_ALIASES["rank"])

    if not inst_col or not country_col:
        raise ValueError(f"Could not find institution/country columns. Found: {list(df.columns)}")

    rows = []
    for _, row in df.iterrows():
        name    = str(row[inst_col]).strip()
        country = _iso2(str(row[country_col]))
        rank    = _parse_rank(row[rank_col]) if rank_col else None

        if not name or name == "nan":
            continue

        rows.append({
            "name":                name,
            "country":             country,
            "ranking_qs":          rank,
            "data_source":         "qs_kaggle",
            "tuition_usd_per_year": 0,   # placeholder; update via scorecard or manual
        })

    print(f"Parsed {len(rows)} universities from {csv_path}")

    inserted = 0
    batch_size = 100
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        if update:
            res = await client.table("universities").upsert(
                batch,
                on_conflict="name,country",
                ignore_duplicates=False,
            ).execute()
        else:
            res = await client.table("universities").insert(
                batch,
                upsert=False,
            ).execute()
        inserted += len(res.data or [])
        print(f"  Batch {i // batch_size + 1}: {len(res.data or [])} rows")

    print(f"Total inserted/updated: {inserted}")
    return inserted


def main():
    parser = argparse.ArgumentParser(description="Import QS Rankings CSV into Supabase")
    parser.add_argument("--file", required=True, help="Path to QS Rankings CSV file")
    parser.add_argument("--update", action="store_true", help="Upsert (update existing rows)")
    args = parser.parse_args()

    asyncio.run(import_rankings(args.file, update=args.update))


if __name__ == "__main__":
    main()
