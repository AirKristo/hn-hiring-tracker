"""
collect_comments.py

Downloads every comment from each Who is Hiring thread listed in
data/processed/threads.csv, saving one JSON file per thread to data/raw/.

We store all comments, including replies, and filter to top-level job
postings later in parse_postings.py. Keeping the raw layer unfiltered means
we never have to re-download to answer a new question.

Already-downloaded threads are skipped, so this script is safe to re-run
and resumes where it left off.
"""

import json
import os
import time

import pandas as pd
import requests

ALGOLIA_SEARCH_BY_DATE_URL = "https://hn.algolia.com/api/v1/search_by_date"
HITS_PER_PAGE = 1000
REQUEST_DELAY_SECONDS = 1
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 5

THREADS_PATH = "data/processed/threads.csv"
RAW_DIRECTORY = "data/raw"


def raw_path_for_thread(thread_id):
    return os.path.join(RAW_DIRECTORY, f"comments_{thread_id}.json")


def request_with_retries(parameters):
    """GET the Algolia search endpoint, retrying on transient failures."""
    for attempt_number in range(MAX_RETRIES):
        try:
            response = requests.get(ALGOLIA_SEARCH_BY_DATE_URL, params=parameters, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            is_last_attempt = (attempt_number == MAX_RETRIES - 1)

            if is_last_attempt:
                raise

            wait_seconds = RETRY_BACKOFF_SECONDS * (attempt_number + 1)
            print(f"    Request failed ({error}), retrying in {wait_seconds}s")
            time.sleep(wait_seconds)


def collect_comments_for_thread(thread_id):
    """
    Return every comment belonging to one thread, replies included.
    """
    comments_by_id = {}
    oldest_timestamp_seen = None

    while True:
        parameters = {
            "tags": f"comment,story_{thread_id}",
            "hitsPerPage": HITS_PER_PAGE,
        }

        if oldest_timestamp_seen is not None:
            parameters["numericFilters"] = f"created_at_i<={oldest_timestamp_seen}"

        payload = request_with_retries(parameters)
        hits = payload["hits"]

        if len(hits) == 0:
            break

        new_comment_count = 0

        for hit in hits:
            comment_id = hit["objectID"]

            if comment_id not in comments_by_id:
                comments_by_id[comment_id] = hit
                new_comment_count = new_comment_count + 1

        if new_comment_count == 0:
            break

        timestamps = [hit["created_at_i"] for hit in hits]
        oldest_timestamp_seen = min(timestamps)

        time.sleep(REQUEST_DELAY_SECONDS)

    return list(comments_by_id.values())


def load_stored_comments(path):
    with open(path, "r", encoding="utf-8") as stored_file:
        return json.load(stored_file)


def store_comments(path, comments):
    with open(path, "w", encoding="utf-8") as output_file:
        json.dump(comments, output_file)


def count_top_level_comments(comments, thread_id):
    """Comments whose parent is the thread itself are the job postings."""
    top_level_count = 0

    for comment in comments:
        if str(comment.get("parent_id")) == str(thread_id):
            top_level_count = top_level_count + 1

    return top_level_count


def main():
    threads = pd.read_csv(THREADS_PATH)
    print(f"Threads to process: {len(threads)}\n")

    collected_count = 0
    skipped_count = 0
    summary_rows = []

    for position, thread in threads.iterrows():
        thread_id = thread["thread_id"]
        label = f"{thread['year']}-{thread['month']:02d}"
        output_path = raw_path_for_thread(thread_id)

        if os.path.exists(output_path):
            skipped_count = skipped_count + 1
            comments = load_stored_comments(output_path)
        else:
            print(f"[{position + 1}/{len(threads)}] {label} — collecting {thread_id}")
            comments = collect_comments_for_thread(thread_id)
            store_comments(output_path, comments)

            collected_count = collected_count + 1
            time.sleep(REQUEST_DELAY_SECONDS)

        top_level_count = count_top_level_comments(comments, thread_id)

        summary_rows.append({
            "thread_id": thread_id,
            "year": thread["year"],
            "month": thread["month"],
            "total_comments": len(comments),
            "top_level_comments": top_level_count,
        })

    summary = pd.DataFrame(summary_rows)

    print(f"\nCollected: {collected_count}   Skipped (already present): {skipped_count}")
    print(f"Total comments stored: {summary['total_comments'].sum():,}")
    print(f"Top-level comments (job postings): {summary['top_level_comments'].sum():,}")

    reply_share = 1 - (summary["top_level_comments"].sum() / summary["total_comments"].sum())
    print(f"Replies as share of all comments: {reply_share:.1%}")

    empty_threads = summary[summary["total_comments"] == 0]
    if len(empty_threads) > 0:
        print(f"\nThreads that returned no comments ({len(empty_threads)}):")
        for _, row in empty_threads.iterrows():
            print(f"  {row['year']}-{row['month']:02d} id={row['thread_id']}")

    summary.to_csv("data/processed/thread_comment_counts.csv", index=False)
    print("\nSaved summary to data/processed/thread_comment_counts.csv")


if __name__ == "__main__":
    main()