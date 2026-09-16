"""
Shared text cleaning used by both the format survey and the parser.

Algolia returns comment_text as an HTML fragment: paragraphs separated by
<p> tags with no newlines, links as full anchor tags, and a mix of HTML
entities (&#x27;) and literal Unicode punctuation.

Contact redaction lives here too. Postings contain recruiter emails, phone
numbers and personal links, which is third-party personal data we do not
publish. It is stripped before anything reaches data/processed/.
"""

import html
import re

HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
PARAGRAPH_BREAK_PATTERN = re.compile(r"<p>")

EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
URL_PATTERN = re.compile(r"https?://\S+|\bwww\.\S+")
PHONE_PATTERN = re.compile(r"\+?\d[\d\s().-]{7,}\d")

SEEKING_WORK_LABELS = [
    "willing to relocate",
    "seeking work",
    "resume:",
    "résumé:",
    "cv:",
    "right to work",
    "availability:",
]


def clean_comment_text(raw_text):
    """Turn an HTML comment fragment into plain text with paragraph breaks."""
    if raw_text is None:
        return ""

    with_breaks = PARAGRAPH_BREAK_PATTERN.sub("\n", raw_text)
    without_tags = HTML_TAG_PATTERN.sub("", with_breaks)
    unescaped = html.unescape(without_tags)

    return unescaped.strip()


def split_header_and_body(clean_text):
    """The first line is the convention header; everything after is the body."""
    parts = clean_text.split("\n", 1)

    header = parts[0].strip()
    body = parts[1].strip() if len(parts) > 1 else ""

    return header, body


def looks_like_seeking_work(clean_text):
    """Two or more candidate-template labels means this is a job seeker."""
    lowercase_text = clean_text.lower()
    matched_count = 0

    for label in SEEKING_WORK_LABELS:
        if label in lowercase_text:
            matched_count = matched_count + 1

    return matched_count >= 2


def contains_contact_info(text):
    has_email = EMAIL_PATTERN.search(text) is not None
    has_url = URL_PATTERN.search(text) is not None

    return has_email or has_url


def redact_contact_info(text):
    """Remove emails, links and phone numbers before the text is published."""
    redacted = EMAIL_PATTERN.sub("[EMAIL]", text)
    redacted = URL_PATTERN.sub("[URL]", redacted)
    redacted = PHONE_PATTERN.sub("[PHONE]", redacted)

    return redacted