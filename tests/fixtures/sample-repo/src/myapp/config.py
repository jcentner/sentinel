"""Application configuration."""

import os

# TODO: Load from environment variables instead of hardcoding
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///myapp.db")
SECRET_KEY = "changeme"
DEBUG = True

# Undocumented env var (not in .env.example)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
