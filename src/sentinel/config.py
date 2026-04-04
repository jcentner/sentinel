"""Configuration loading for Sentinel."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]


@dataclass
class SentinelConfig:
    """Runtime configuration for Sentinel."""

    model: str = "qwen3:4b"
    ollama_url: str = "http://localhost:11434"
    db_path: str = ".sentinel/sentinel.db"
    output_dir: str = ".sentinel"
    skip_judge: bool = False


def load_config(repo_path: str | Path) -> SentinelConfig:
    """Load config from sentinel.toml in the repo root, with defaults."""
    config = SentinelConfig()
    config_file = Path(repo_path) / "sentinel.toml"

    if config_file.exists():
        with open(config_file, "rb") as f:
            data = tomllib.load(f)

        sentinel = data.get("sentinel", {})
        if "model" in sentinel:
            config.model = sentinel["model"]
        if "ollama_url" in sentinel:
            config.ollama_url = sentinel["ollama_url"]
        if "db_path" in sentinel:
            config.db_path = sentinel["db_path"]
        if "output_dir" in sentinel:
            config.output_dir = sentinel["output_dir"]
        if "skip_judge" in sentinel:
            config.skip_judge = sentinel["skip_judge"]

    return config
