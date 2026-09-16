"""
Finds every monthly "Ask HN: Who is hiring?" thread and saves the list
to data/processed/threads.csv.

All of these threads are posted by the 'whoishiring' account, so we pull
that account's submissions rather than searching by title.
Filters out "Who wants to be hired?" and "Freelancer?"
"""

import time

import pandas as pd
import requests
import re

ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
HITS_PER_PAGE = 1000
REQUEST_DELAY_SECONDS = 1
OUTPUT_PATH = "data/processed/threads.csv"


def fetch_whoishiring_submissions():
    """Return every story submitted by the whoishiring account."""
    all_hits = []
    page_number = 0

    while True:
        parameters = {
            "tags": "story,author_whoishiring",
            "hitsPerPage": HITS_PER_PAGE,
            "page": page_number,
        }

        response = requests.get(ALGOLIA_SEARCH_URL, params=parameters, timeout=30)
        response.raise_for_status()
        payload = response.json()

        hits_on_this_page = payload["hits"]
        all_hits.extend(hits_on_this_page)
        print(f"Page {page_number}: {len(hits_on_this_page)} submissions")

        total_pages = payload["nbPages"]
        page_number = page_number + 1

        if page_number >= total_pages:
            break

        time.sleep(REQUEST_DELAY_SECONDS)

    return all_hits

# Matches the monthly cadence: "Ask HN: Who is hiring? (April 2011)".
# Requiring the (Month Year) suffix excludes one-off threads such as the
# 2020 "Who is hiring right now?" post and the 2011 meta thread.
HIRING_THREAD_PATTERN = re.compile(
    r"who is hiring\?\s*\((\w+)\s+(\d{4})\)",
    re.IGNORECASE,
)

# A thread with very few comments is almost certainly broken or superseded
# rather than a genuinely quiet month. December 2011 has 4 comments against
# roughly 290 in neighboring months.
MIN_PLAUSIBLE_COMMENTS = 50


def parse_month_and_year_from_title(title):
    """Return (month_number, year) from the thread title, or None if it doesn't match."""
    if title is None:
        return None

    match = HIRING_THREAD_PATTERN.search(title)
    if match is None:
        return None

    month_name = match.group(1)
    year = int(match.group(2))

    try:
        month_number = pd.to_datetime(month_name, format="%B").month
    except ValueError:
        return None

    return month_number, year


def build_threads_dataframe(hits):
    rows = []

    for hit in hits:
        parsed = parse_month_and_year_from_title(hit.get("title"))

        if parsed is None:
            continue

        month_number, year = parsed

        rows.append({
            "thread_id": hit["objectID"],
            "title": hit["title"],
            "created_at": hit["created_at"],
            "num_comments": hit.get("num_comments"),
            "points": hit.get("points"),
            "year": year,
            "month": month_number,
        })

    threads = pd.DataFrame(rows)
    threads["created_at"] = pd.to_datetime(threads["created_at"]).dt.tz_localize(None)
    threads = threads.sort_values(["year", "month"]).reset_index(drop=True)

    return threads


def report_duplicate_months(threads):
    """Each month should appear exactly once."""
    counts_per_month = threads.groupby(["year", "month"]).size()
    duplicated_months = counts_per_month[counts_per_month > 1]

    if len(duplicated_months) == 0:
        print("No duplicate months.")
    else:
        print(f"Duplicate months found:\n{duplicated_months}")


def report_suspect_threads(threads):
    """Flag threads too small to be a real month of postings."""
    suspect_threads = threads[threads["num_comments"] < MIN_PLAUSIBLE_COMMENTS]

    if len(suspect_threads) == 0:
        print("No suspiciously small threads.")
    else:
        print(f"Suspiciously small threads ({len(suspect_threads)}):")
        for _, row in suspect_threads.iterrows():
            print(f"  {row['year']}-{row['month']:02d} "
                  f"id={row['thread_id']} comments={row['num_comments']}")


def report_missing_months(threads):
    """Flag calendar months with no hiring thread, so gaps are known up front."""
    observed_months = pd.PeriodIndex.from_fields(
        year=threads["year"],
        month=threads["month"],
        freq="M",
    )

    expected_months = pd.period_range(
        observed_months.min(),
        observed_months.max(),
        freq="M",
    )
    missing_months = expected_months.difference(observed_months)

    print(f"Expected months in range: {len(expected_months)}")
    print(f"Observed months: {len(observed_months)}")

    if len(missing_months) == 0:
        print("No missing months.")
    else:
        print(f"Missing months ({len(missing_months)}): {list(missing_months)}")


def main():
    hits = fetch_whoishiring_submissions()
    print(f"\nTotal submissions by whoishiring: {len(hits)}")

    threads = build_threads_dataframe(hits)

    print(f"Monthly hiring threads: {len(threads)}")
    print(f"Date range: {threads['created_at'].min().date()} "
          f"to {threads['created_at'].max().date()}")
    print(f"Total comments across all threads: {threads['num_comments'].sum():,.0f}")
    print()

    report_missing_months(threads)
    report_duplicate_months(threads)
    report_suspect_threads(threads)

    threads.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()