# Phase 7: Provider Abstraction

> **Status**: Not Started
> **Prerequisites**: Phase 6 complete (semantic-drift validated, test-code coherence shipped), Phase 6b in progress or complete
> **Goal**: Make the pipeline provider-agnostic, not just model-agnostic. Users choose their own model + provider combination via config. See [ADR-010](../../docs/architecture/decisions/010-pluggable-model-provider.md).

## Key Principle

Opinionated defaults, extensible everything. Ollama remains the zero-config default. Cloud providers are an explicit opt-in.

## Acceptance Criteria

1. `ModelProvider` protocol with `generate()`, `embed()`, `check_health()`
2. `OllamaProvider` extracts current behavior — zero change for existing users
3. `OpenAICompatibleProvider` covers Azure OpenAI, OpenAI direct, and any compatible endpoint
4. Config: `provider = "ollama"` (default) or `provider = "openai"` with `api_base`, `api_key_env`
5. API keys read from environment variables only, never stored in config files
6. Judge, semantic-drift, and docs-drift call `provider.generate()` instead of raw `httpx.post`
7. Embedding calls go through `provider.embed()`
8. `sentinel doctor` checks the configured provider's health
9. Cloud provider logs a startup warning: "Provider 'openai' configured — code excerpts will be sent to {api_base}"
10. All existing tests pass without modification (Ollama remains the test default)
11. Provider-level tests mock at the protocol boundary

## Implementation Slices

### Slice 1: ModelProvider protocol + OllamaProvider extraction

**Files**: `src/sentinel/core/provider.py` (new), `src/sentinel/core/ollama.py` (refactor)

**What**:
1. Define `ModelProvider` protocol and `LLMResponse` dataclass in `provider.py`
2. Implement `OllamaProvider` — extract the 3 existing `httpx.post` call sites (judge, semantic-drift, docs-drift) plus `embed_texts()` and `check_ollama()` into a single provider class
3. Add `get_provider(config) -> ModelProvider` factory function
4. Wire judge.py, semantic_drift.py, docs_drift.py, context.py, indexer.py to call provider methods instead of raw HTTP

**Test**: All existing tests pass. New unit tests for `OllamaProvider` methods.

### Slice 2: OpenAICompatibleProvider

**Files**: `src/sentinel/core/provider.py` (extend)

**What**:
1. Implement `OpenAICompatibleProvider` using `/v1/chat/completions` and `/v1/embeddings`
2. Handle Azure OpenAI URL patterns (deployment-based URLs)
3. API key from environment variable (read `os.environ[config.api_key_env]`)
4. Map `LLMResponse` fields from OpenAI response format
5. `check_health()` via a lightweight models list call or a minimal completion

**Test**: Unit tests with mocked HTTP responses. No live API calls in CI.

### Slice 3: Config + CLI updates

**Files**: `src/sentinel/config.py`, `src/sentinel/cli.py`

**What**:
1. Add `provider`, `api_base`, `api_key_env` to `SentinelConfig`
2. Update `sentinel init` to include provider config in generated `sentinel.toml`
3. Update `sentinel doctor` to check the configured provider
4. Add `--provider` CLI override
5. Startup warning when cloud provider is configured

**Test**: Config validation tests, doctor output tests.

### Slice 4: Documentation + README

Update README with provider configuration examples (Ollama default, Azure OpenAI, OpenAI direct).

## Design Decisions

- **Two providers, not a plugin system**: `OllamaProvider` and `OpenAICompatibleProvider` cover all known use cases. OpenAI-compatible is a de facto standard that covers Azure, OpenAI, vLLM, LM Studio, Together, and more. Entry-point plugin system deferred unless a genuinely different provider type emerges.
- **Single provider per run**: One provider handles both generation and embedding. Supporting different providers for generation vs embedding adds config complexity with minimal benefit. Can be revisited.
- **`api_key_env`, not `api_key`**: The config file names the environment variable, never contains the secret. Same pattern as the existing `GITHUB_TOKEN`.
- **No streaming for v1**: All current consumers use non-streaming responses. Streaming can be added to the protocol later without breaking existing providers.

## Open Questions

- **OQ-010**: Exact protocol surface (see [open-questions.md](../../docs/reference/open-questions.md))
