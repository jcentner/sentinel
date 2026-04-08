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
