# ADR-010: Pluggable model provider interface

**Status**: Accepted
**Date**: 2026-04-07
**Deciders**: Project founder
**Supersedes**: ADR-003 (Model-agnostic design via Ollama)

## Context

ADR-003 established model-agnosticism via Ollama: model names are config, not code, and the pipeline works regardless of which model is loaded. This achieved swappable *models* but hardcoded a single *provider* — every LLM call is a raw `httpx.post` to Ollama's `/api/generate` or `/api/embed` endpoint with Ollama-proprietary JSON payloads.

Three forces push beyond this:

1. **Real user demand**: A colleague wants to run Sentinel with Azure OpenAI, using more powerful models (GPT-5.4-nano, GLM-5) for deeper analysis than a 4B local model can deliver.
2. **Capability ceiling**: The current binary "needs review" signal is a smart constraint for 4B models, but users with more powerful models are artificially limited. A 9B local model, a Haiku 4.5, or a frontier cloud model could deliver structured analysis — explaining *what* is wrong, not just *that* something is wrong.
3. **Contributor friction**: Requiring Ollama setup to use or contribute to Sentinel limits adoption. Many developers already have OpenAI API keys or Azure credits.

The Ollama coupling is thin (4 files with direct API calls, 3 more for config/wiring), making this a low-risk refactor.

## Decision

Introduce a `ModelProvider` protocol that abstracts all model interaction behind a common interface. Providers are pluggable — selected via config, not code.

### Provider protocol

```python
class ModelProvider(Protocol):
    def generate(self, prompt: str, *, system: str | None = None,
                 temperature: float = 0.1, max_tokens: int = 512,
                 num_ctx: int = 2048, json_output: bool = False) -> LLMResponse: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def check_health(self) -> bool: ...
```

`LLMResponse` is a simple dataclass containing `text`, `token_count`, and `duration_ms` — the common subset needed by all consumers (judge, detectors, logging).

### Shipped providers

- **`OllamaProvider`** (default): Current behavior extracted. Calls `/api/generate` and `/api/embed`. Zero-config for existing users.
- **`OpenAICompatibleProvider`**: Covers OpenAI direct and any OpenAI-compatible endpoint (vLLM, LM Studio, Together, etc.). Uses the standard `/v1/chat/completions` and `/v1/embeddings` endpoints. API key via environment variable.
- **`AzureProvider`**: Azure AI Foundry. Uses Entra ID (Azure AD) bearer tokens acquired via `az account get-access-token`. Targets the `/openai/v1/chat/completions` and `/openai/v1/embeddings` endpoints. Uses `max_completion_tokens` (not `max_tokens`) for compatibility with newer Azure models. No API key needed — authentication is handled by the Azure CLI.

### Configuration

```toml
# Default — no change from current behavior
provider = "ollama"
model = "qwen3.5:4b"
ollama_url = "http://localhost:11434"

# OpenAI-compatible provider (API key in env var)
provider = "openai"
model = "gpt-5.4-nano"
api_base = "https://api.openai.com"
api_key_env = "OPENAI_API_KEY"

# Azure AI Foundry (Entra ID auth via az CLI)
provider = "azure"
model = "gpt-5.4-nano"
api_base = "https://my-resource.services.ai.azure.com"
```

For `openai` provider, API keys are **never** stored in config files. The `api_key_env` field names the environment variable to read.

For `azure` provider, no API key is needed. Authentication uses Entra ID tokens from `az account get-access-token --resource https://cognitiveservices.azure.com`. Tokens are cached and auto-refreshed.

### Capability tiers

Detectors and the judge can declare a minimum capability tier:

| Tier | Model class | Examples | What it enables |
|------|-------------|----------|-----------------|
| `basic` | 4B+ local | qwen3.5:4b | Binary triage signals, structured judge verdicts |
| `standard` | 9B+ local or small cloud | qwen3:9b, Haiku 4.5 | Structured analysis with reasoning, test-code coherence |
| `advanced` | Frontier cloud | GPT-5.4-nano, GLM-5, Sonnet | Deep reasoning, subtle intent comparison, detailed explanations |

Capability tier is **informational, not enforced** — the system warns if a detector's declared tier exceeds the configured model's expected capability, but does not block execution. Users know their models better than we do.

### Privacy model

Local-first by default. Code never leaves the machine unless the user explicitly configures a cloud provider. When a cloud provider is configured, the system logs a clear startup message: "Provider 'openai' configured — code excerpts will be sent to {api_base}."

## Consequences

**Positive**:
- Users choose their own model + provider combination. Sentinel works with local Ollama, Azure OpenAI, direct OpenAI, or any compatible endpoint.
- Unlocks capability-tiered detectors: more powerful models enable deeper analysis.
- Lowers contributor friction — no Ollama requirement for development/testing with a cloud provider.
- Existing users experience zero change — Ollama remains the default.
- Cleaner codebase: the 3 separate `httpx.post` call sites consolidate behind `provider.generate()`.

**Negative**:
- Testing surface grows (two provider implementations to maintain). Mitigated by mocking at the protocol boundary.
- Privacy story requires nuance: "local-first by default" instead of "always local."
- Provider-specific quirks (rate limits, token counting, error shapes) must be normalized in each provider implementation.

**Neutral**:
- ADR-003's core insight holds: the value is in the pipeline, not the model. This ADR extends the same principle from model-agnostic to provider-agnostic.
- ADR-001 (local-first) remains accurate — local is the default. Cloud is an explicit, informed user choice.

## Alternatives considered

- **Ollama-only, let users proxy**: Users could point `ollama_url` at an OpenAI-compatible proxy like LiteLLM. Works but is clunky, undocumented, and puts the abstraction burden on the user.
- **LiteLLM as a dependency**: Python library that wraps 100+ providers. Adds a large dependency tree and maintenance risk for a system that uses exactly two endpoints (`generate` and `embed`).
- **Full plugin system (entry points)**: Over-engineered for two providers. Can be added later if a third provider type emerges.
