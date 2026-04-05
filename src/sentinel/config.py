"""Configuration loading for Sentinel."""

# NOTE: no `from __future__ import annotations` here — we need
# dataclasses.fields() to return real types, not annotation strings.

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


class ConfigError(ValueError):
    """Raised when sentinel.toml contains invalid values."""


@dataclass
class SentinelConfig:
    """Runtime configuration for Sentinel."""

    model: str = "qwen3.5:4b"
    ollama_url: str = "http://localhost:11434"
    db_path: str = ".sentinel/sentinel.db"
    output_dir: str = ".sentinel"
    skip_judge: bool = False


# Expected types for each config field, derived from the dataclass defaults.
# Without `from __future__ import annotations`, f.type is the real type (str, bool, etc.).
_FIELD_TYPES: dict[str, type] = {f.name: f.type for f in fields(SentinelConfig)}


def _validate_config(sentinel: dict, config_file: Path) -> None:
    """Validate types of sentinel.toml values against the dataclass schema."""
    for key, value in sentinel.items():
        if key not in _FIELD_TYPES:
            raise ConfigError(
                f"{config_file}: unknown config key '{key}'. "
                f"Valid keys: {', '.join(_FIELD_TYPES)}"
            )
        expected_type = _FIELD_TYPES[key]
        if not isinstance(value, expected_type):
            raise ConfigError(
                f"{config_file}: '{key}' must be {expected_type.__name__}, "
                f"got {type(value).__name__}: {value!r}"
            )


def load_config(repo_path: str | Path) -> SentinelConfig:
    """Load config from sentinel.toml in the repo root, with defaults."""
    config = SentinelConfig()
    config_file = Path(repo_path) / "sentinel.toml"

    if config_file.exists():
        with open(config_file, "rb") as f:
            data = tomllib.load(f)

        sentinel = data.get("sentinel", {})
        _validate_config(sentinel, config_file)

        for key, value in sentinel.items():
            setattr(config, key, value)

    return config
