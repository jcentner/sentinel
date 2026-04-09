"""Tests for sentinel.config — loading and validation."""

from __future__ import annotations

import pytest

from sentinel.config import ConfigError, load_config


def test_defaults_without_config_file(tmp_path):
    """No sentinel.toml → all defaults."""
    config = load_config(tmp_path)
    assert config.model == "qwen3.5:4b"
    assert config.skip_judge is False


def test_loads_valid_config(tmp_path):
    (tmp_path / "sentinel.toml").write_text(
        '[sentinel]\nmodel = "llama3:8b"\nskip_judge = true\n'
    )
    config = load_config(tmp_path)
    assert config.model == "llama3:8b"
    assert config.skip_judge is True


def test_rejects_wrong_type_for_model(tmp_path):
    (tmp_path / "sentinel.toml").write_text("[sentinel]\nmodel = 42\n")
    with pytest.raises(ConfigError, match="'model' must be str"):
        load_config(tmp_path)


def test_rejects_wrong_type_for_skip_judge(tmp_path):
    (tmp_path / "sentinel.toml").write_text('[sentinel]\nskip_judge = "yes"\n')
    with pytest.raises(ConfigError, match="'skip_judge' must be bool"):
        load_config(tmp_path)


def test_rejects_unknown_key(tmp_path):
    (tmp_path / "sentinel.toml").write_text("[sentinel]\nfoo = 1\n")
    with pytest.raises(ConfigError, match="unknown config key 'foo'"):
        load_config(tmp_path)


def test_partial_config_keeps_defaults(tmp_path):
    (tmp_path / "sentinel.toml").write_text('[sentinel]\nmodel = "gemma:2b"\n')
    config = load_config(tmp_path)
    assert config.model == "gemma:2b"
    assert config.ollama_url == "http://localhost:11434"  # default preserved


def test_loads_custom_num_ctx(tmp_path):
    (tmp_path / "sentinel.toml").write_text("[sentinel]\nnum_ctx = 4096\n")
    config = load_config(tmp_path)
    assert config.num_ctx == 4096


def test_rejects_wrong_type_for_num_ctx(tmp_path):
    (tmp_path / "sentinel.toml").write_text('[sentinel]\nnum_ctx = "big"\n')
    with pytest.raises(ConfigError, match="'num_ctx' must be int"):
        load_config(tmp_path)


def test_rejects_invalid_model_capability(tmp_path):
    (tmp_path / "sentinel.toml").write_text(
        '[sentinel]\nmodel_capability = "turbo"\n'
    )
    with pytest.raises(ConfigError, match="model_capability"):
        load_config(tmp_path)


def test_accepts_valid_model_capability(tmp_path):
    for cap in ("none", "basic", "standard", "advanced"):
        (tmp_path / "sentinel.toml").write_text(
            f'[sentinel]\nmodel_capability = "{cap}"\n'
        )
        config = load_config(tmp_path)
        assert config.model_capability == cap


def test_enabled_detectors_defaults_empty(tmp_path):
    config = load_config(tmp_path)
    assert config.enabled_detectors == []
    assert config.disabled_detectors == []


def test_loads_enabled_detectors(tmp_path):
    (tmp_path / "sentinel.toml").write_text(
        '[sentinel]\nenabled_detectors = ["todo-scanner", "docs-drift"]\n'
    )
    config = load_config(tmp_path)
    assert config.enabled_detectors == ["todo-scanner", "docs-drift"]
    assert config.disabled_detectors == []


def test_loads_disabled_detectors(tmp_path):
    (tmp_path / "sentinel.toml").write_text(
        '[sentinel]\ndisabled_detectors = ["complexity"]\n'
    )
    config = load_config(tmp_path)
    assert config.disabled_detectors == ["complexity"]
    assert config.enabled_detectors == []


def test_rejects_both_enabled_and_disabled(tmp_path):
    (tmp_path / "sentinel.toml").write_text(
        '[sentinel]\nenabled_detectors = ["a"]\ndisabled_detectors = ["b"]\n'
    )
    with pytest.raises(ConfigError, match="cannot set both"):
        load_config(tmp_path)


def test_rejects_non_string_detector_names(tmp_path):
    (tmp_path / "sentinel.toml").write_text(
        "[sentinel]\nenabled_detectors = [1, 2]\n"
    )
    with pytest.raises(ConfigError, match="list of strings"):
        load_config(tmp_path)


# ── Per-detector provider config (OQ-012) ──────────────────────────

def test_detector_providers_defaults_empty(tmp_path):
    config = load_config(tmp_path)
    assert config.detector_providers == {}


def test_loads_detector_providers(tmp_path):
    (tmp_path / "sentinel.toml").write_text(
        '[sentinel]\n'
        '[sentinel.detector_providers.semantic-drift]\n'
        'provider = "azure"\n'
        'model = "gpt-5.4-nano"\n'
        'api_base = "https://example.services.ai.azure.com"\n'
    )
    config = load_config(tmp_path)
    assert "semantic-drift" in config.detector_providers
    override = config.detector_providers["semantic-drift"]
    assert override.provider == "azure"
    assert override.model == "gpt-5.4-nano"
    assert override.api_base == "https://example.services.ai.azure.com"


def test_detector_providers_partial_override(tmp_path):
    (tmp_path / "sentinel.toml").write_text(
        '[sentinel]\n'
        '[sentinel.detector_providers.test-coherence]\n'
        'model = "llama3:8b"\n'
    )
    config = load_config(tmp_path)
    override = config.detector_providers["test-coherence"]
    assert override.model == "llama3:8b"
    assert override.provider == ""  # empty = inherit global
    assert override.api_base == ""


def test_detector_providers_multiple_detectors(tmp_path):
    (tmp_path / "sentinel.toml").write_text(
        '[sentinel]\n'
        '[sentinel.detector_providers.semantic-drift]\n'
        'provider = "azure"\n'
        'model = "gpt-5.4-nano"\n'
        '[sentinel.detector_providers.test-coherence]\n'
        'model = "llama3:8b"\n'
    )
    config = load_config(tmp_path)
    assert len(config.detector_providers) == 2
    assert config.detector_providers["semantic-drift"].provider == "azure"
    assert config.detector_providers["test-coherence"].model == "llama3:8b"


def test_detector_providers_rejects_unknown_key(tmp_path):
    (tmp_path / "sentinel.toml").write_text(
        '[sentinel]\n'
        '[sentinel.detector_providers.semantic-drift]\n'
        'turbo = true\n'
    )
    with pytest.raises(ConfigError, match="unknown key 'turbo'"):
        load_config(tmp_path)


def test_detector_providers_rejects_non_string_value(tmp_path):
    (tmp_path / "sentinel.toml").write_text(
        '[sentinel]\n'
        '[sentinel.detector_providers.semantic-drift]\n'
        'model = 42\n'
    )
    with pytest.raises(ConfigError, match="must be a string"):
        load_config(tmp_path)


def test_detector_providers_with_capability_override(tmp_path):
    (tmp_path / "sentinel.toml").write_text(
        '[sentinel]\n'
        'model_capability = "basic"\n'
        '[sentinel.detector_providers.semantic-drift]\n'
        'provider = "openai"\n'
        'api_base = "https://api.openai.com"\n'
        'model_capability = "advanced"\n'
    )
    config = load_config(tmp_path)
    assert config.model_capability == "basic"
    override = config.detector_providers["semantic-drift"]
    assert override.model_capability == "advanced"


def test_detector_providers_coexists_with_global_config(tmp_path):
    (tmp_path / "sentinel.toml").write_text(
        '[sentinel]\n'
        'model = "qwen3.5:4b"\n'
        'provider = "ollama"\n'
        '[sentinel.detector_providers.semantic-drift]\n'
        'provider = "openai"\n'
        'model = "gpt-5.4-nano"\n'
        'api_base = "https://api.openai.com"\n'
    )
    config = load_config(tmp_path)
    assert config.provider == "ollama"
    assert config.model == "qwen3.5:4b"
    assert config.detector_providers["semantic-drift"].provider == "openai"
