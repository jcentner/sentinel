"""Configuration loading for Sentinel."""

# NOTE: no `from __future__ import annotations` here — we need
# dataclasses.fields() to return real types, not annotation strings.

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when sentinel.toml contains invalid values."""


@dataclass
class SentinelConfig:
    """Runtime configuration for Sentinel."""

    # Provider selection (see ADR-010)
    provider: str = "ollama"
    model: str = "qwen3.5:4b"
    ollama_url: str = "http://localhost:11434"
    api_base: str = ""
    api_key_env: str = ""
    db_path: str = ".sentinel/sentinel.db"
    output_dir: str = ".sentinel"
    skip_judge: bool = False
    embed_model: str = ""
    embed_chunk_size: int = 50
    embed_chunk_overlap: int = 10
    detectors_dir: str = ""
    num_ctx: int = 2048
    model_capability: str = "basic"  # none, basic, standard, advanced


# Expected types for each config field, derived from the dataclass defaults.
# Without `from __future__ import annotations`, f.type is the real type (str, bool, etc.).
_FIELD_TYPES: dict[str, type] = {
    f.name: f.type for f in fields(SentinelConfig)  # type: ignore[misc]
}


_VALID_CAPABILITIES = frozenset({"none", "basic", "standard", "advanced"})


def _validate_config(sentinel: dict[str, Any], config_file: Path) -> None:
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

    cap = sentinel.get("model_capability")
    if cap is not None and cap not in _VALID_CAPABILITIES:
        raise ConfigError(
            f"{config_file}: 'model_capability' must be one of "
            f"{sorted(_VALID_CAPABILITIES)}, got {cap!r}"
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
