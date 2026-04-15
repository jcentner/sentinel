# Architecture

High-level architecture of the MyApp system.

## Security

All passwords are hashed with bcrypt before storage. The login handler
verifies credentials against bcrypt hashes — plaintext comparison is
never used.

## Notifications

The notification service supports multiple delivery channels including
email and SMS. Users can configure their preferred channels in their
profile settings. By default, both email and SMS are active.

## Data Integrity

Orders follow a strict status lifecycle: pending → processing →
shipped → delivered. Invalid transitions are rejected with a
ValueError. Refunds are only available for pending and processing orders.

## Configuration

Application configuration is loaded from environment variables
documented in `.env.example`. The `REDIS_URL` setting controls the
caching backend. All environment variables are documented in the
example file.
