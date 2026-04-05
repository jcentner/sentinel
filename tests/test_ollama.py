"""Tests for the Ollama utility module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from sentinel.core.ollama import check_ollama, embed_texts

# ── check_ollama ─────────────────────────────────────────────────────


class TestCheckOllama:
    def test_success(self):
        mock_resp = MagicMock(status_code=200)
        with patch("httpx.get", return_value=mock_resp):
            assert check_ollama("http://localhost:11434") is True

    def test_non_200(self):
        mock_resp = MagicMock(status_code=500)
        with patch("httpx.get", return_value=mock_resp):
            assert check_ollama("http://localhost:11434") is False

    def test_connection_error(self):
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            assert check_ollama("http://localhost:11434") is False

    def test_timeout(self):
        with patch("httpx.get", side_effect=httpx.TimeoutException("timed out")):
            assert check_ollama("http://localhost:11434") is False


# ── embed_texts ──────────────────────────────────────────────────────


class TestEmbedTexts:
    def test_empty_input(self):
        result = embed_texts([], "model")
        assert result == []

    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "embeddings": [[0.1, 0.2], [0.3, 0.4]],
        }
        with patch("httpx.post", return_value=mock_resp):
            result = embed_texts(["hello", "world"], "model")

        assert result == [[0.1, 0.2], [0.3, 0.4]]

    def test_non_200_status(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        with patch("httpx.post", return_value=mock_resp):
            result = embed_texts(["hello"], "model")

        assert result is None

    def test_missing_embeddings_key(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"somethingelse": []}
        with patch("httpx.post", return_value=mock_resp):
            result = embed_texts(["hello"], "model")

        assert result is None

    def test_exception_returns_none(self):
        with patch("httpx.post", side_effect=RuntimeError("network error")):
            result = embed_texts(["hello"], "model")

        assert result is None

    def test_uses_correct_url_and_payload(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"embeddings": [[0.1]]}
        with patch("httpx.post", return_value=mock_resp) as mock_post:
            embed_texts(["text1"], "my-model", "http://custom:1234")

        mock_post.assert_called_once_with(
            "http://custom:1234/api/embed",
            json={"model": "my-model", "input": ["text1"]},
            timeout=120.0,
        )
