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


# ── AzureProvider ────────────────────────────────────────────────────


class TestAzureProvider:
    def _make_provider(self, **kwargs):
        from sentinel.core.providers.azure import AzureProvider

        defaults = {
            "model": "gpt-5.4-nano",
            "api_base": "https://myresource.services.ai.azure.com",
        }
        defaults.update(kwargs)
        return AzureProvider(**defaults)

    def test_satisfies_protocol(self):
        provider = self._make_provider()
        assert isinstance(provider, ModelProvider)

    def test_factory_creates_azure_provider(self):
        from sentinel.config import SentinelConfig
        from sentinel.core.providers.azure import AzureProvider

        config = SentinelConfig(
            provider="azure",
            model="gpt-5.4-nano",
            api_base="https://myresource.services.ai.azure.com",
        )
        p = create_provider(config)
        assert isinstance(p, AzureProvider)
        assert p.model == "gpt-5.4-nano"

    def test_azure_requires_api_base(self):
        from sentinel.config import SentinelConfig

        config = SentinelConfig(provider="azure", model="test")
        with pytest.raises(ValueError, match="api_base"):
            create_provider(config)

    def test_completions_url_appends_openai(self):
        provider = self._make_provider()
        url = provider._completions_url()
        assert url == "https://myresource.services.ai.azure.com/openai/v1/chat/completions"

    def test_completions_url_preserves_existing_openai_suffix(self):
        provider = self._make_provider(
            api_base="https://myresource.services.ai.azure.com/openai"
        )
        url = provider._completions_url()
        assert url == "https://myresource.services.ai.azure.com/openai/v1/chat/completions"

    def test_embeddings_url(self):
        provider = self._make_provider()
        url = provider._embeddings_url()
        assert url == "https://myresource.services.ai.azure.com/openai/v1/embeddings"

    def test_token_acquisition(self):
        provider = self._make_provider()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"accessToken": "test-token-123", "expiresOn": "2099-01-01 00:00:00.000000"}'

        with patch("subprocess.run", return_value=mock_result):
            token = provider._ensure_token()

        assert token == "test-token-123"

    def test_token_caching(self):
        """Token should be cached and not re-acquired on second call."""
        provider = self._make_provider()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"accessToken": "cached-token", "expiresOn": "2099-01-01 00:00:00.000000"}'

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            token1 = provider._ensure_token()
            token2 = provider._ensure_token()

        assert token1 == token2 == "cached-token"
        assert mock_run.call_count == 1  # Only called once

    def test_token_refresh_on_expiry(self):
        """Expired token should trigger re-acquisition."""
        provider = self._make_provider()
        provider._token = "old-token"
        provider._token_expires_at = 0.0  # Already expired

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"accessToken": "new-token", "expiresOn": "2099-01-01 00:00:00.000000"}'

        with patch("subprocess.run", return_value=mock_result):
            token = provider._ensure_token()

        assert token == "new-token"

    def test_token_failure_raises(self):
        provider = self._make_provider()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Not logged in"

        with patch("subprocess.run", return_value=mock_result), pytest.raises(RuntimeError, match="az account get-access-token failed"):
            provider._ensure_token()

    def test_az_cli_not_found_raises(self):
        provider = self._make_provider()

        with patch("subprocess.run", side_effect=FileNotFoundError), pytest.raises(RuntimeError, match="Azure CLI.*not found"):
            provider._ensure_token()

    def test_generate_success(self):
        provider = self._make_provider()
        provider._token = "test-token"
        provider._token_expires_at = 9999999999.0

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello from Azure!"}}],
            "usage": {"completion_tokens": 5},
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            result = provider.generate("Hi", system="Be helpful")

        assert result.text == "Hello from Azure!"
        assert result.token_count == 5
        payload = mock_post.call_args.kwargs["json"]
        assert payload["model"] == "gpt-5.4-nano"
        assert payload["max_completion_tokens"] == 512
        assert "max_tokens" not in payload
        assert payload["messages"][0] == {"role": "system", "content": "Be helpful"}
        assert payload["messages"][1] == {"role": "user", "content": "Hi"}
        # Check auth header
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer test-token"

    def test_generate_json_mode(self):
        provider = self._make_provider()
        provider._token = "test-token"
        provider._token_expires_at = 9999999999.0

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

    def test_embed_success(self):
        provider = self._make_provider(embed_model="text-embedding-3-small")
        provider._token = "test-token"
        provider._token_expires_at = 9999999999.0

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

        assert result == [[0.1, 0.2], [0.3, 0.4]]

    def test_embed_no_model_returns_none(self):
        provider = self._make_provider()
        assert provider.embed(["text"]) is None

    def test_embed_empty_input(self):
        provider = self._make_provider(embed_model="test")
        assert provider.embed([]) == []

    def test_check_health_success(self):
        provider = self._make_provider()
        provider._token = "test-token"
        provider._token_expires_at = 9999999999.0

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        with patch("httpx.get", return_value=mock_resp):
            assert provider.check_health() is True

    def test_check_health_no_token(self):
        """Health check fails if we can't get a token."""
        provider = self._make_provider()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Not logged in"

        with patch("subprocess.run", return_value=mock_result):
            assert provider.check_health() is False

    def test_repr(self):
        provider = self._make_provider()
        r = repr(provider)
        assert "AzureProvider" in r
        assert "gpt-5.4-nano" in r
