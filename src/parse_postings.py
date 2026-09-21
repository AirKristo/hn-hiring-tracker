"""
parse_postings.py

Turns raw comments into a tidy postings table at data/processed/postings.parquet.

Extraction is keyword-based across the header rather than positional. The
format survey showed companies drop fields rather than reorder them, so
"segment 2 is always location" does not hold. Company name is the exception:
segment 0 is reliably the company.

Three things learned from inspecting real postings:

  Salary ranges must be matched as a single unit. Matching figures
  independently collapsed "$150-200k" to a flat 200k, because the dollar
  sign binds to the first number and the k to the second.

  Currency must be read from a narrow window around the matched figure, and
  an explicit code beats a symbol. "$140k CAD" is Canadian pay written with
  a dollar sign; scanning the whole posting for "$" called it USD.

  Remote status is read from the header only. Scanning the full comment
  produced a large bucket where "remote" appeared incidentally in body
  prose. Postings routinely offer both arrangements, so remote and onsite
  are independent flags rather than one categorical.

Location and role extraction live in locations.py and roles.py.

Contact details are redacted before anything is written to data/processed/.
"""

import json
import os
import re

import pandas as pd

from locations import extract_location_flags
from roles import extract_role_flags
from text_utils import (
    clean_comment_text,
    contains_contact_info,
    looks_like_seeking_work,
    redact_contact_info,
    split_header_and_body,
)

RAW_DIRECTORY = "data/raw"
THREADS_PATH = "data/processed/threads.csv"
OUTPUT_PATH = "data/processed/postings.parquet"

MINIMUM_PLAUSIBLE_SALARY = 30_000
MAXIMUM_PLAUSIBLE_SALARY = 1_000_000

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}
CURRENCY_CONTEXT_CHARACTERS = 25

CURRENCY_CODE_PATTERN = re.compile(
    r"\b(USD|CAD|AUD|NZD|EUR|GBP|CHF|SEK|NOK|DKK|INR|SGD|JPY)\b"
)

RETIREMENT_PLAN_PATTERN = re.compile(r"\b40[13]\s*\(?[kb]\)?\b", re.IGNORECASE)

LARGE_MONEY_PATTERN = re.compile(r"[$€£]\s*\d+(?:\.\d+)?\s*[mbMB]\b")

MONTHLY_RATE_PATTERN = re.compile(r"(?:/|per\s+)\s*(?:month|mo|hour|hr)\b", re.IGNORECASE)

SALARY_RANGE_PATTERN = re.compile(
    r"(?P<symbol1>[$€£])?\s*(?P<amount1>\d{1,3}(?:,\d{3})+|\d{2,3})\s*(?P<k1>[kK])?"
    r"\s*(?:-|–|—|to)\s*"
    r"(?P<symbol2>[$€£])?\s*(?P<amount2>\d{1,3}(?:,\d{3})+|\d{2,3})\s*(?P<k2>[kK])?"
)

SINGLE_SALARY_PATTERN = re.compile(
    r"(?P<symbol>[$€£])?\s*(?P<amount>\d{1,3}(?:,\d{3})+)\s*(?P<k>[kK])?"
    r"|(?P<symbol2>[$€£])\s*(?P<amount2>\d{2,3})\s*(?P<k2>[kK])"
)

REMOTE_PATTERN = re.compile(r"\bremote\b|\bwfh\b|\bwork from home\b", re.IGNORECASE)
ONSITE_PATTERN = re.compile(r"\bon-?site\b|\bin-?office\b|\bin person\b", re.IGNORECASE)
HYBRID_PATTERN = re.compile(r"\bhybrid\b", re.IGNORECASE)
NO_REMOTE_PATTERN = re.compile(r"\bno remote\b|\bnot remote\b|\bremote:\s*no\b", re.IGNORECASE)
WORLDWIDE_PATTERN = re.compile(r"\bworldwide\b|\banywhere\b|\bglobal\b", re.IGNORECASE)


def strip_non_salary_money(text):
    """Remove retirement plans and funding figures before salary matching."""
    without_retirement = RETIREMENT_PLAN_PATTERN.sub(" ", text)
    without_funding = LARGE_MONEY_PATTERN.sub(" ", without_retirement)

    return without_funding


def context_around(text, match):
    """Return the matched text plus a small window on either side."""
    start = max(0, match.start() - CURRENCY_CONTEXT_CHARACTERS)
    end = min(len(text), match.end() + CURRENCY_CONTEXT_CHARACTERS)

    return text[start:end]


def detect_currency(matched_text, surrounding_text):
    """
    Determine currency from the matched figure and its immediate context.

    An explicit code wins over a symbol, because "$140k CAD" and "$100k AUD"
    both use a dollar sign for a non-USD currency.
    """
    code_match = CURRENCY_CODE_PATTERN.search(surrounding_text)

    if code_match is not None:
        return code_match.group(1)

    for symbol, currency_code in CURRENCY_SYMBOLS.items():
        if symbol in matched_text:
            return currency_code

    return None


def scale_amount(amount_text, has_k_marker, sibling_has_k_marker):
    """
    Convert a matched figure to an annual number.

    In "$150-200k" only the second figure carries the k, but it applies to
    both. sibling_has_k_marker passes that along.
    """
    amount = float(amount_text.replace(",", ""))

    if has_k_marker or sibling_has_k_marker:
        if amount < 1000:
            amount = amount * 1000

    return amount


def is_plausible_salary(amount):
    return MINIMUM_PLAUSIBLE_SALARY <= amount <= MAXIMUM_PLAUSIBLE_SALARY


def extract_salary_range(searchable, full_text):
    """Try to read a two-figure salary range. Returns None if not found."""
    range_match = SALARY_RANGE_PATTERN.search(searchable)

    if range_match is None:
        return None

    has_k1 = range_match.group("k1") is not None
    has_k2 = range_match.group("k2") is not None
    has_symbol = (range_match.group("symbol1") is not None
                  or range_match.group("symbol2") is not None)

    if not has_k1 and not has_k2 and not has_symbol:
        return None

    low_value = scale_amount(range_match.group("amount1"), has_k1, has_k2)
    high_value = scale_amount(range_match.group("amount2"), has_k2, has_k1)

    if not is_plausible_salary(low_value):
        return None

    if not is_plausible_salary(high_value):
        return None

    if low_value > high_value:
        return None

    surrounding = context_around(searchable, range_match)
    currency = detect_currency(range_match.group(0), surrounding)

    return low_value, high_value, currency


def extract_single_salary(searchable, full_text):
    """Try to read a single salary figure. Returns None if not found."""
    single_match = SINGLE_SALARY_PATTERN.search(searchable)

    if single_match is None:
        return None

    amount_text = single_match.group("amount") or single_match.group("amount2")

    if amount_text is None:
        return None

    has_k = (single_match.group("k") is not None
             or single_match.group("k2") is not None)
    symbol = single_match.group("symbol") or single_match.group("symbol2")

    if not has_k and symbol is None:
        return None

    amount = scale_amount(amount_text, has_k, False)

    if not is_plausible_salary(amount):
        return None

    surrounding = context_around(searchable, single_match)
    currency = detect_currency(single_match.group(0), surrounding)

    return amount, amount, currency


def extract_salary(text):
    """
    Return (low, high, currency). A single figure yields low == high.
    Returns (None, None, None) when nothing plausible is found.
    """
    searchable = strip_non_salary_money(text)

    if MONTHLY_RATE_PATTERN.search(searchable) is not None:
        return None, None, None

    range_result = extract_salary_range(searchable, text)

    if range_result is not None:
        return range_result

    single_result = extract_single_salary(searchable, text)

    if single_result is not None:
        return single_result

    return None, None, None


def extract_remote_flags(header):
    """
    Return (mentions_remote, mentions_onsite, is_hybrid, is_worldwide_remote).

    Read from the header only. Postings frequently offer both arrangements
    ("ONSITE NYC or REMOTE (US)"), so remote and onsite are independent.
    """
    if NO_REMOTE_PATTERN.search(header) is not None:
        return False, True, False, False

    mentions_remote = REMOTE_PATTERN.search(header) is not None
    mentions_onsite = ONSITE_PATTERN.search(header) is not None
    is_hybrid = HYBRID_PATTERN.search(header) is not None
    is_worldwide_remote = mentions_remote and WORLDWIDE_PATTERN.search(header) is not None

    return mentions_remote, mentions_onsite, is_hybrid, is_worldwide_remote


def extract_company(header):
    """Segment 0 of the pipe header is reliably the company name."""
    if "|" not in header:
        return None

    company = header.split("|")[0].strip()

    if len(company) == 0:
        return None

    if len(company) > 80:
        return None

    return company


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


def build_postings(threads):
    rows = []

    for _, thread in threads.iterrows():
        thread_id = thread["thread_id"]

        for comment in load_top_level_comments(thread_id):
            clean_text = clean_comment_text(comment["comment_text"])

            if looks_like_seeking_work(clean_text):
                continue

            header, body = split_header_and_body(clean_text)

            salary_low, salary_high, currency = extract_salary(clean_text)

            mentions_remote, mentions_onsite, is_hybrid, is_worldwide_remote = \
                extract_remote_flags(header)

            posting = {
                "comment_id": comment["objectID"],
                "thread_id": thread_id,
                "year": thread["year"],
                "month": thread["month"],
                "company": extract_company(header),
                "has_pipe_header": "|" in header,
                "mentions_remote": mentions_remote,
                "mentions_onsite": mentions_onsite,
                "is_hybrid": is_hybrid,
                "is_worldwide_remote": is_worldwide_remote,
                "salary_low": salary_low,
                "salary_high": salary_high,
                "salary_currency": currency,
                "had_contact_info": contains_contact_info(clean_text),
                "header": redact_contact_info(header),
                "body_length": len(body),
            }

            posting.update(extract_location_flags(header))
            posting.update(extract_role_flags(header))

            rows.append(posting)

    return pd.DataFrame(rows)


def report_coverage(postings):
    print(f"Postings parsed: {len(postings):,}\n")

    in_window = postings[postings["year"] >= 2016]
    print(f"Postings from 2016 onward: {len(in_window):,}\n")

    print("Field coverage, 2016 onward:")
    print(f"  company:      {in_window['company'].notna().mean():.1%}")
    print(f"  salary:       {in_window['salary_low'].notna().mean():.1%}")
    print(f"  location:     {in_window['location_found'].mean():.1%}")
    print(f"  role:         {in_window['role_found'].mean():.1%}")

    print("\nWork arrangement, 2016 onward (header only):")
    print(f"  mentions remote:     {in_window['mentions_remote'].mean():.1%}")
    print(f"  mentions onsite:     {in_window['mentions_onsite'].mean():.1%}")
    print(f"  hybrid:              {in_window['is_hybrid'].mean():.1%}")
    print(f"  worldwide remote:    {in_window['is_worldwide_remote'].mean():.1%}")

    remote_not_onsite = in_window["mentions_remote"] & ~in_window["mentions_onsite"]
    print(f"  remote, not onsite:  {remote_not_onsite.mean():.1%}")

    print("\nLocation coverage, 2016 onward:")
    print(f"  US mentioned:        {in_window['mentions_any_us'].mean():.1%}")
    print(f"  non-US mentioned:    {in_window['mentions_non_us'].mean():.1%}")
    print(f"  NYC:                 {in_window['mentions_nyc'].mean():.1%}")
    print(f"  California:          {in_window['mentions_california'].mean():.1%}")

    print("\nRole share by year (share of postings mentioning each family):")
    role_columns = [
        "role_ai_ml", "role_data_science", "role_data_engineering",
        "role_data_analyst", "role_software_engineer", "role_infrastructure",
        "role_security", "role_mobile", "role_product", "role_design",
    ]

    header_labels = "  year  " + " ".join(
        name.replace("role_", "")[:8].rjust(8) for name in role_columns
    )
    print(header_labels)

    for year in sorted(in_window["year"].unique()):
        year_rows = in_window[in_window["year"] == year]
        shares = []

        for column in role_columns:
            shares.append(f"{year_rows[column].mean():>7.1%} ")

        print(f"  {year} " + " ".join(shares))

    print("\nSeniority share by year:")
    for year in sorted(in_window["year"].unique()):
        year_rows = in_window[in_window["year"] == year]
        print(f"  {year}  senior {year_rows['seniority_senior'].mean():>5.1%}   "
              f"junior {year_rows['seniority_junior'].mean():>5.1%}   "
              f"founding {year_rows['seniority_founding'].mean():>5.1%}")

    print("\nSalary coverage by year:")
    by_year = postings.groupby("year")["salary_low"].agg(["count", "size"])
    for year, row in by_year.iterrows():
        share = row["count"] / row["size"]
        print(f"  {year}  {share:>5.1%}  (n={row['size']:,})")

    print("\nExtracted salary distribution (USD only, 2016 onward):")
    usd_salaries = in_window[in_window["salary_currency"] == "USD"]["salary_low"]
    if len(usd_salaries) > 0:
        print(f"  n:       {len(usd_salaries):,}")
        print(f"  p10:     {usd_salaries.quantile(0.10):>10,.0f}")
        print(f"  median:  {usd_salaries.median():>10,.0f}")
        print(f"  p90:     {usd_salaries.quantile(0.90):>10,.0f}")

    print(f"\nPostings that contained contact info (now redacted): "
          f"{postings['had_contact_info'].mean():.1%}")


def main():
    threads = pd.read_csv(THREADS_PATH)
    postings = build_postings(threads)

    report_coverage(postings)

    postings.to_parquet(OUTPUT_PATH, index=False)
    print(f"\nSaved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()