# API Reference

Developer reference for the MyApp public API.

## Utilities

### `format_currency(amount, currency)`

Formats a monetary amount as a human-readable string with two decimal places.
Returns strings like `"$12.50"` for USD or `"€25.00"` for EUR.

### `parse_date(date_str)`

Parses date strings in both ISO 8601 (`2024-01-15`) and RFC 2822
(`Mon, 15 Jan 2024`) formats. Returns a dict with `year`, `month`, `day`.

### `slugify(text)`

Converts arbitrary text to a URL-friendly slug. Lowercases, replaces
spaces with hyphens, strips non-alphanumeric characters.

### `hash_file(path)`

Computes the SHA-256 hex digest of a file. Reads in 8KB chunks for
memory efficiency. Returns a 64-character lowercase hex string.

## Data Processing

### `process_records(records, config)`

Validates and transforms a list of record dicts. Returns a dict with
`results`, `errors`, and `total` keys.

Supports three record types: `user`, `event`, and `metric`. Enable
`strict_mode` in config to reject unknown types.

## Authentication

### `handle_login(request)`

Authenticates a user by verifying their password against stored bcrypt
hashes. Returns a session token on success.

### `handle_register(request)`

Creates a new user account and dispatches an async welcome email via
the notification service.

### `handle_search(query, filters)`

Searches users with fuzzy matching (Levenshtein distance) for
approximate queries. Supports filtering by role and active status.

## Orders

### `calculate_shipping(order)`

Calculates shipping cost. Orders over $50 qualify for free shipping.
Standard domestic rate is $5.99, international is $15.99.

### `generate_report(start_date, end_date)`

Generates a summary report for the date range as PDF bytes, ready for
download or email attachment.

## Architecture Notes

All user passwords are hashed with bcrypt before storage. Plaintext
passwords are never persisted or compared directly.

The notification service dispatches messages to multiple channels
(email and SMS) depending on user preferences.
