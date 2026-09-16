"""
inspect_parsing.py

Prints samples of real postings so we can check what the parser is doing
before trusting any of it.

Read-only. Writes nothing.
"""

import pandas as pd

POSTINGS_PATH = "data/processed/postings.parquet"
SAMPLE_SIZE = 25
RANDOM_SEED = 1


def print_section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main():
    postings = pd.read_parquet(POSTINGS_PATH)
    recent = postings[postings["year"] >= 2024]

    print_section("A. Headers where NO salary was found")
    no_salary = recent[recent["salary_low"].isna() & recent["has_pipe_header"]]
    for header in no_salary["header"].sample(SAMPLE_SIZE, random_state=RANDOM_SEED):
        print(header)

    print_section("B. Headers mentioning both remote and onsite")
    both = recent[recent["mentions_remote"] & recent["mentions_onsite"]]
    for header in both["header"].sample(SAMPLE_SIZE, random_state=RANDOM_SEED):
        print(header)

    print_section("C. Salaries we DID extract — are these real pay?")
    found = recent[recent["salary_low"].notna()]
    sample = found.sample(20, random_state=RANDOM_SEED)
    for _, row in sample.iterrows():
        print(f"{row['salary_low']:>10,.0f} - {row['salary_high']:>10,.0f} "
              f"{str(row['salary_currency']):<5} | {row['header'][:110]}")


if __name__ == "__main__":
    main()