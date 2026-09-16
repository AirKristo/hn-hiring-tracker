"""
survey_format.py

Measures the actual structure of the postings before any field extraction.

Three things we need to know:
  1. How many top-level comments are real job postings vs. candidates
     posting the "Who wants to be hired?" template in the wrong thread.
  2. How many follow the "Company | Role | Location | ..." pipe convention.
  3. How the number of pipe segments is distributed, and whether the
     convention has drifted across 15 years.

Nothing is parsed into fields here. This script only tells us what the
parser has to handle.
"""

import glob
import html
import json
import os
import re

import pandas as pd
from text_utils import clean_comment_text, split_header_and_body, looks_like_seeking_work

RAW_DIRECTORY = "data/raw"
THREADS_PATH = "data/processed/threads.csv"

# Algolia returns comment_text as an HTML fragment. Paragraphs are separated
# by <p> tags with no newlines, and links appear as full anchor tags.
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
PARAGRAPH_BREAK_PATTERN = re.compile(r"<p>")

# Labels used by the "Who wants to be hired?" template. A comment using
# several of these is a candidate advertising themselves, not an employer.
SEEKING_WORK_LABELS = [
    "willing to relocate",
    "seeking work",
    "resume:",
    "résumé:",
    "cv:",
    "right to work",
    "availability:",
]


def count_seeking_work_labels(clean_text):
    lowercase_text = clean_text.lower()
    matched_count = 0

    for label in SEEKING_WORK_LABELS:
        if label in lowercase_text:
            matched_count = matched_count + 1

    return matched_count


def load_top_level_comments(thread_id):
    path = os.path.join(RAW_DIRECTORY, f"comments_{thread_id}.json")

    with open(path, "r", encoding="utf-8") as raw_file:
        comments = json.load(raw_file)

    top_level = []

    for comment in comments:
        if str(comment.get("parent_id")) != str(thread_id):
            continue

        if comment.get("comment_text") is None:
            continue

        top_level.append(comment)

    return top_level


def build_survey_rows(threads):
    rows = []

    for _, thread in threads.iterrows():
        thread_id = thread["thread_id"]
        comments = load_top_level_comments(thread_id)

        for comment in comments:
            clean_text = clean_comment_text(comment["comment_text"])
            header, body = split_header_and_body(clean_text)

            rows.append({
                "thread_id": thread_id,
                "year": thread["year"],
                "month": thread["month"],
                "comment_id": comment["objectID"],
                "header": header,
                "header_length": len(header),
                "body_length": len(body),
                "pipe_count": header.count("|"),
                "is_seeking_work": looks_like_seeking_work(clean_text),
            })

    return pd.DataFrame(rows)


def report_survey(survey):
    total_count = len(survey)
    print(f"Top-level comments with text: {total_count:,}\n")

    seeking_work_count = survey["is_seeking_work"].sum()
    print(f"Look like candidate posts (wrong template): "
          f"{seeking_work_count:,} ({seeking_work_count / total_count:.1%})")

    postings = survey[~survey["is_seeking_work"]]
    print(f"Treated as employer postings: {len(postings):,}\n")

    has_pipes = postings["pipe_count"] > 0
    print(f"Postings with a pipe-delimited header: "
          f"{has_pipes.sum():,} ({has_pipes.mean():.1%})\n")

    print("Pipe segment counts (pipes + 1):")
    segment_counts = (postings["pipe_count"] + 1).value_counts().sort_index()
    for segment_count, frequency in segment_counts.items():
        if frequency >= 50:
            print(f"  {segment_count:>2} segments: {frequency:>6,} "
                  f"({frequency / len(postings):>5.1%})")

    print("\nPipe-header adoption by year:")
    by_year = postings.groupby("year").agg(
        postings=("comment_id", "count"),
        pipe_share=("pipe_count", lambda values: (values > 0).mean()),
        median_segments=("pipe_count", lambda values: values.median() + 1),
    )
    for year, row in by_year.iterrows():
        print(f"  {year}  n={row['postings']:>5,.0f}  "
              f"pipe={row['pipe_share']:>5.1%}  "
              f"median segments={row['median_segments']:.0f}")

    print("\nCandidate-post contamination by year:")
    contamination_by_year = survey.groupby("year")["is_seeking_work"].mean()
    for year, share in contamination_by_year.items():
        print(f"  {year}  {share:.1%}")


def main():
    threads = pd.read_csv(THREADS_PATH)
    survey = build_survey_rows(threads)

    report_survey(survey)

    survey.to_csv("data/processed/format_survey.csv", index=False)
    print("\nSaved survey to data/processed/format_survey.csv")


if __name__ == "__main__":
    main()