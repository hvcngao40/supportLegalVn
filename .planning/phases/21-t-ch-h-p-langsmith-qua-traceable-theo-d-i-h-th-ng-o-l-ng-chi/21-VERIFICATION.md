---
status: passed
phase: 21-t-ch-h-p-langsmith-qua-traceable-theo-d-i-h-th-ng-o-l-ng-chi
updated: 2026-06-23
---

# Phase 21 Verification

## Automated checks

- **Integration tests:** PASS
  - `pytest tests/test_langsmith_integration.py` completed successfully with 6/6 tests passing.
  - Verification includes:
    - Centralized pricing calculator (`calculate_token_cost()`) maps and calculates costs correctly.
    - Decoupled fail-safe wrapper does not break execution when LangSmith is missing or disabled.
    - `GeminiClient`, `GroqClient`, and `DeepSeekClient` correctly record metadata with token usage and cost.
    - `LegalRAGPipeline` correctly sets `cache_hit` and `token_cost_usd` on Cache Hits.

- **API Route Tracing:** PASS
  - Public routes (`/ask`, `/stream`, `GET /stream`, and `/search-articles`) in `api/v1/endpoints.py` are decorated with `@traceable` wrapper.
  - Sub-spans for dynamic classifier, vector retriever, SQLite FTS, and cache checks are established.
