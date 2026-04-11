"""Configuration loading for Sentinel."""

# NOTE: no `from __future__ import annotations` here — we need
# dataclasses.fields() to return real types, not annotation strings.

import contextlib
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when sentinel.toml contains invalid values."""


@dataclass
class ProviderOverride:
    """Per-detector provider override configuration.

    Any field left as empty string inherits from the global SentinelConfig.
    """

    provider: str = ""
    model: str = ""
    api_base: str = ""
    api_key_env: str = ""
    model_capability: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any], detector_name: str, config_file: Path) -> "ProviderOverride":
        """Create a ProviderOverride from a TOML dict, validating types."""
        valid_keys = {f.name for f in fields(cls)}
        for key, value in data.items():
            if key not in valid_keys:
                raise ConfigError(
                    f"{config_file}: unknown key '{key}' in "
                    f"[sentinel.detector_providers.{detector_name}]. "
                    f"Valid keys: {', '.join(sorted(valid_keys))}"
                )
            if not isinstance(value, str):
                raise ConfigError(
                    f"{config_file}: '{key}' in "
                    f"[sentinel.detector_providers.{detector_name}] "
                    f"must be a string, got {type(value).__name__}: {value!r}"
                )
        cap = data.get("model_capability", "")
        if cap and cap not in _VALID_CAPABILITIES:
            raise ConfigError(
                f"{config_file}: 'model_capability' in "
                f"[sentinel.detector_providers.{detector_name}] "
                f"must be one of {sorted(_VALID_CAPABILITIES)}, got {cap!r}"
            )
        return cls(**data)


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
    skip_llm: bool = False
    embed_model: str = ""
    embed_chunk_size: int = 50
    embed_chunk_overlap: int = 10
    detectors_dir: str = ""
    num_ctx: int = 2048
    model_capability: str = "basic"  # none, basic, standard, advanced
    min_confidence: float = 0.0  # Findings below this threshold excluded from report (0 = show all)
    enabled_detectors: list = field(default_factory=list)  # type: ignore[type-arg]
    disabled_detectors: list = field(default_factory=list)  # type: ignore[type-arg]
    # Per-detector provider overrides (OQ-012)
    detector_providers: dict = field(default_factory=dict)  # type: ignore[type-arg]


# Expected types for each config field, derived from the dataclass defaults.
# Without `from __future__ import annotations`, f.type is the real type (str, bool, etc.).
_FIELD_TYPES: dict[str, type] = {
    f.name: f.type for f in fields(SentinelConfig)  # type: ignore[misc]
}


_VALID_CAPABILITIES = frozenset({"none", "basic", "standard", "advanced"})


def _validate_config(sentinel: dict[str, Any], config_file: Path) -> None:
    """Validate types of sentinel.toml values against the dataclass schema."""
    for key, value in sentinel.items():
        # detector_providers is a nested dict — validated separately
        if key == "detector_providers":
            if not isinstance(value, dict):
                raise ConfigError(
                    f"{config_file}: 'detector_providers' must be a table, "
                    f"got {type(value).__name__}"
                )
            continue
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

    # Validate list-of-string fields
    for list_key in ("enabled_detectors", "disabled_detectors"):
        val = sentinel.get(list_key)
        if val is not None and not all(isinstance(item, str) for item in val):
            raise ConfigError(
                f"{config_file}: '{list_key}' must be a list of strings"
            )

    enabled = sentinel.get("enabled_detectors")
    disabled = sentinel.get("disabled_detectors")
    if enabled and disabled:
        raise ConfigError(
            f"{config_file}: cannot set both 'enabled_detectors' and "
            f"'disabled_detectors' — use one or the other"
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

        # Parse per-detector provider overrides before setting flat fields
        raw_dp = sentinel.pop("detector_providers", None)
        if raw_dp is not None:
            dp: dict[str, ProviderOverride] = {}
            for det_name, det_cfg in raw_dp.items():
                if not isinstance(det_cfg, dict):
                    raise ConfigError(
                        f"{config_file}: detector_providers.{det_name} must be a table"
                    )
                dp[det_name] = ProviderOverride.from_dict(det_cfg, det_name, config_file)
            config.detector_providers = dp

        for key, value in sentinel.items():
            setattr(config, key, value)

    return config


def _toml_value(value: object) -> str:
    """Format a Python value as a TOML literal."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        # Escape for TOML basic strings (backslash, quotes, and control chars)
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        escaped = (
            escaped.replace("\n", "\\n")
            .replace("\r", "\\r")
            .replace("\t", "\\t")
            .replace("\b", "\\b")
            .replace("\f", "\\f")
        )
        return f'"{escaped}"'
    if isinstance(value, list):
        items = ", ".join(_toml_value(item) for item in value)
        return f"[{items}]"
    raise ConfigError(f"Cannot serialize {type(value).__name__} to TOML: {value!r}")


def save_config(repo_path: str | Path, config: SentinelConfig) -> Path:
    """Write config to sentinel.toml in the repo root.

    Writes only fields that differ from defaults to keep the file clean.
    Uses atomic write (temp file + rename) for safety.

    Returns the path to the written config file.
    """
    import os
    import tempfile

    defaults = SentinelConfig()
    config_file = Path(repo_path) / "sentinel.toml"

    lines: list[str] = ["[sentinel]"]

    # Write non-default scalar fields
    for f in fields(SentinelConfig):
        if f.name == "detector_providers":
            continue  # Handled separately below
        current = getattr(config, f.name)
        default = getattr(defaults, f.name)
        if current != default:
            lines.append(f"{f.name} = {_toml_value(current)}")

    # Write detector provider overrides
    if config.detector_providers:
        lines.append("")  # Blank line before sub-tables
        for det_name, override in sorted(config.detector_providers.items()):
            lines.append(f"[sentinel.detector_providers.{det_name}]")
            override_defaults = ProviderOverride()
            for of in fields(ProviderOverride):
                val = getattr(override, of.name)
                if val != getattr(override_defaults, of.name):
                    lines.append(f"{of.name} = {_toml_value(val)}")

    content = "\n".join(lines) + "\n"

    # Atomic write: write to temp file in same directory, then rename
    config_file.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(config_file.parent), suffix=".tmp", prefix=".sentinel-"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, str(config_file))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise

    return config_file
