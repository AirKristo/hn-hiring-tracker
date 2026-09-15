"""
fetch_threads.py

Finds every monthly "Ask HN: Who is hiring?" thread and saves the list
to data/processed/threads.csv.

All of these threads are posted by the 'whoishiring' account, so we pull
that account's submissions rather than searching by title.
Filters out "Who wants to be hired?" and "Freelancer?"
"""

import time

import pandas as pd
import requests

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


def is_hiring_thread(title):
    """True for 'Who is hiring?' threads, false for the other monthly threads."""
    if title is None:
        return False

    lowercase_title = title.lower()
    return "who is hiring" in lowercase_title


def build_threads_dataframe(hits):
    rows = []

    for hit in hits:
        if not is_hiring_thread(hit.get("title")):
            continue

        rows.append({
            "thread_id": hit["objectID"],
            "title": hit["title"],
            "created_at": hit["created_at"],
            "num_comments": hit.get("num_comments"),
            "points": hit.get("points"),
        })

    threads = pd.DataFrame(rows)
    threads["created_at"] = pd.to_datetime(threads["created_at"])
    threads = threads.sort_values("created_at").reset_index(drop=True)
    threads["year"] = threads["created_at"].dt.year
    threads["month"] = threads["created_at"].dt.month

    return threads


def report_missing_months(threads):
    """Flag any calendar months with no hiring thread, so gaps are known up front."""
    first_month = threads["created_at"].min().to_period("M")
    last_month = threads["created_at"].max().to_period("M")

    expected_months = pd.period_range(first_month, last_month, freq="M")
    observed_months = threads["created_at"].dt.to_period("M")
    missing_months = expected_months.difference(observed_months)

    if len(missing_months) == 0:
        print("No missing months.")
    else:
        print(f"Missing months ({len(missing_months)}): {list(missing_months)}")


def main():
    hits = fetch_whoishiring_submissions()
    print(f"\nTotal submissions by whoishiring: {len(hits)}")

    threads = build_threads_dataframe(hits)

    print(f"Who is hiring threads: {len(threads)}")
    print(f"Date range: {threads['created_at'].min().date()} "
          f"to {threads['created_at'].max().date()}")
    print(f"Total comments across all threads: {threads['num_comments'].sum():,.0f}")

    report_missing_months(threads)

    threads.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()