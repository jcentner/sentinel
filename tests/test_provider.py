"""Tests for the model provider protocol and implementations."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sentinel.core.provider import LLMResponse, ModelProvider, create_provider

# ── Protocol compliance ──────────────────────────────────────────────


class TestModelProviderProtocol:
    def test_mock_provider_satisfies_protocol(self):
        from tests.mock_provider import MockProvider

        p = MockProvider()
        assert isinstance(p, ModelProvider)

    def test_ollama_provider_satisfies_protocol(self):
        from sentinel.core.providers.ollama import OllamaProvider

        p = OllamaProvider(model="test")
        assert isinstance(p, ModelProvider)

    def test_openai_provider_satisfies_protocol(self):
        from sentinel.core.providers.openai_compat import OpenAICompatibleProvider

        p = OpenAICompatibleProvider(model="test", api_base="http://localhost")
        assert isinstance(p, ModelProvider)


class TestLLMResponse:
    def test_immutable(self):
        r = LLMResponse(text="hello")
        with pytest.raises(AttributeError):
            r.text = "bye"  # type: ignore[misc]

    def test_defaults(self):
        r = LLMResponse(text="ok")
        assert r.token_count is None
        assert r.duration_ms is None


# ── Factory ──────────────────────────────────────────────────────────


class TestCreateProvider:
    def test_creates_ollama_provider(self):
        from sentinel.config import SentinelConfig
        from sentinel.core.providers.ollama import OllamaProvider

        config = SentinelConfig(provider="ollama", model="qwen3.5:4b")
        p = create_provider(config)
        assert isinstance(p, OllamaProvider)
        assert p.model == "qwen3.5:4b"

    def test_creates_openai_provider(self):
        from sentinel.config import SentinelConfig
        from sentinel.core.providers.openai_compat import OpenAICompatibleProvider

        config = SentinelConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_base="https://api.example.com",
        )
        p = create_provider(config)
        assert isinstance(p, OpenAICompatibleProvider)
        assert p.model == "gpt-4o-mini"
        assert p.api_base == "https://api.example.com"

    def test_openai_requires_api_base(self):
        from sentinel.config import SentinelConfig

        config = SentinelConfig(provider="openai", model="test")
        with pytest.raises(ValueError, match="api_base"):
            create_provider(config)

    def test_unknown_provider_raises(self):
        from sentinel.config import SentinelConfig

        config = SentinelConfig(provider="unknown")
        with pytest.raises(ValueError, match="Unknown provider"):
            create_provider(config)


# ── OllamaProvider ───────────────────────────────────────────────────


class TestOllamaProvider:
    def _make_provider(self, **kwargs):
        from sentinel.core.providers.ollama import OllamaProvider

        defaults = {"model": "test-model", "ollama_url": "http://localhost:11434"}
        defaults.update(kwargs)
        return OllamaProvider(**defaults)

    def test_generate_success(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "response": "Hello world",
            "eval_count": 5,
            "eval_duration": 1_000_000_000,  # 1 second in nanoseconds
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            result = provider.generate("Say hello", system="Be helpful")

        assert result.text == "Hello world"
        assert result.token_count == 5
        assert result.duration_ms == pytest.approx(1000.0)
        call_args = mock_post.call_args
        payload = call_args.kwargs["json"]
        assert payload["model"] == "test-model"
        assert payload["prompt"] == "Say hello"
        assert payload["system"] == "Be helpful"
        assert payload["stream"] is False

    def test_generate_json_mode(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": '{"key": "val"}'}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            provider.generate("Return JSON", json_output=True)

        payload = mock_post.call_args.kwargs["json"]
        assert payload["format"] == "json"

    def test_embed_success(self):
        provider = self._make_provider(embed_model="nomic-embed-text")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "embeddings": [[0.1, 0.2], [0.3, 0.4]],
        }

        with patch("httpx.post", return_value=mock_resp):
            result = provider.embed(["text1", "text2"])

        assert result == [[0.1, 0.2], [0.3, 0.4]]

    def test_embed_no_model_returns_none(self):
        provider = self._make_provider(embed_model="")
        assert provider.embed(["text"]) is None

    def test_embed_empty_input(self):
        provider = self._make_provider(embed_model="test")
        assert provider.embed([]) == []

    def test_embed_failure_returns_none(self):
        provider = self._make_provider(embed_model="test")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch("httpx.post", return_value=mock_resp):
            result = provider.embed(["text"])
        assert result is None

    def test_check_health_success(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.get", return_value=mock_resp):
            assert provider.check_health() is True

    def test_check_health_unreachable(self):
        provider = self._make_provider()
        import httpx

        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            assert provider.check_health() is False

    def test_repr(self):
        provider = self._make_provider()
        r = repr(provider)
        assert "OllamaProvider" in r
        assert "test-model" in r


# ── OpenAICompatibleProvider ─────────────────────────────────────────


class TestOpenAICompatibleProvider:
    def _make_provider(self, **kwargs):
        from sentinel.core.providers.openai_compat import OpenAICompatibleProvider

        defaults = {
            "model": "gpt-4o-mini",
            "api_base": "https://api.example.com",
        }
        defaults.update(kwargs)
        return OpenAICompatibleProvider(**defaults)

    def test_generate_success(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}}],
            "usage": {"completion_tokens": 3},
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            result = provider.generate("Hi", system="Sys prompt")

        assert result.text == "Hello!"
        assert result.token_count == 3
        assert result.duration_ms is not None
        payload = mock_post.call_args.kwargs["json"]
        assert payload["messages"] == [
            {"role": "system", "content": "Sys prompt"},
            {"role": "user", "content": "Hi"},
        ]

    def test_generate_json_mode(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"a": 1}'}}],
            "usage": {},
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            provider.generate("JSON", json_output=True)

        payload = mock_post.call_args.kwargs["json"]
        assert payload["response_format"] == {"type": "json_object"}

    def test_generate_no_system(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {},
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            provider.generate("Hello")

        payload = mock_post.call_args.kwargs["json"]
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"

    def test_embed_success(self):
        provider = self._make_provider(embed_model="text-embedding-3-small")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"index": 1, "embedding": [0.3, 0.4]},
                {"index": 0, "embedding": [0.1, 0.2]},
            ],
        }

        with patch("httpx.post", return_value=mock_resp):
            result = provider.embed(["a", "b"])

        # Should sort by index
        assert result == [[0.1, 0.2], [0.3, 0.4]]

    def test_embed_empty_input(self):
        provider = self._make_provider(embed_model="test")
        assert provider.embed([]) == []

    def test_embed_no_model_returns_none(self):
        provider = self._make_provider(embed_model="")
        assert provider.embed(["text"]) is None

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        provider = self._make_provider(api_key_env="OPENAI_API_KEY")
        headers = provider._headers()
        assert headers["Authorization"] == "Bearer sk-test-key"

    def test_no_api_key_env(self):
        provider = self._make_provider()
        headers = provider._headers()
        assert "Authorization" not in headers

    def test_check_health_success(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.get", return_value=mock_resp):
            assert provider.check_health() is True

    def test_check_health_404_still_healthy(self):
        """404 means server is up but endpoint doesn't exist — still healthy."""
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("httpx.get", return_value=mock_resp):
            assert provider.check_health() is True

    def test_check_health_500_unhealthy(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        with patch("httpx.get", return_value=mock_resp):
            assert provider.check_health() is False

    def test_check_health_unreachable(self):
        provider = self._make_provider()
        import httpx

        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            assert provider.check_health() is False

    def test_repr(self):
        provider = self._make_provider()
        r = repr(provider)
        assert "OpenAICompatibleProvider" in r
        assert "gpt-4o-mini" in r
