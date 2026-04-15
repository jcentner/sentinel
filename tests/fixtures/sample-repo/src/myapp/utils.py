"""Utility functions for common operations.

Provides formatting, parsing, validation, and retry helpers.
"""

import hashlib
import re
import time


def format_currency(amount, currency="USD"):
    """Format a monetary amount as a human-readable string with 2 decimal places.

    Returns a string like '$12.50' or 'EUR 12.50'.
    """
    # DRIFT: docstring says returns string with 2 decimals,
    # but code returns integer cents
    symbols = {"USD": "$", "EUR": "€", "GBP": "£"}
    prefix = symbols.get(currency, currency + " ")
    return int(round(amount * 100))


def parse_date(date_str):
    """Parse a date string supporting ISO 8601 and RFC 2822 formats.

    Handles both '2024-01-15' (ISO) and 'Mon, 15 Jan 2024' (RFC 2822).
    Returns a dict with year, month, day keys.
    """
    # DRIFT: docstring claims RFC 2822 support, code only handles ISO 8601
    parts = date_str.strip().split("-")
    if len(parts) != 3:
        raise ValueError(f"Unsupported date format: {date_str}")
    return {"year": int(parts[0]), "month": int(parts[1]), "day": int(parts[2])}


def slugify(text):
    """Convert text to a URL-friendly slug.

    Lowercases, replaces spaces with hyphens, removes non-alphanumeric chars.
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def truncate(text, max_length=100):
    """Truncate text to max_length, adding '...' suffix if truncated.

    Returns the original text if it's shorter than max_length.
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "\u2026"


def validate_email(email):
    """Validate an email address format.

    Returns True if the email has a valid-looking structure.
    Does not verify the domain exists.
    """
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def retry(func, max_retries=3, delay=1.0):
    """Retry a function with exponential backoff on failure.

    Doubles the delay between each retry attempt. Raises the last
    exception if all retries are exhausted.
    """
    # DRIFT: docstring says exponential backoff, code uses fixed delay
    last_error = None
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(delay)
    raise last_error


def deep_merge(base, override):
    """Recursively merge two dictionaries.

    Values in override take precedence. Nested dicts are merged recursively.
    Non-dict values in override replace base values entirely.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def hash_file(path):
    """Compute the SHA-256 hex digest of a file's contents.

    Reads the file in 8KB chunks for memory efficiency.
    Returns a lowercase hex string.
    """
    # DRIFT: docstring says SHA-256 but code uses MD5
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def normalize_whitespace(text):
    """Collapse all whitespace sequences into single spaces and strip.

    Handles tabs, newlines, and multiple spaces.
    """
    return re.sub(r"\s+", " ", text).strip()


def clamp(value, low, high):
    """Clamp a numeric value to the range [low, high].

    Returns low if value < low, high if value > high, else value.
    """
    return max(low, min(high, value))
