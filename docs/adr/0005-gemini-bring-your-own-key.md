# 0005: Gemini, bring your own key, behind a provider interface

Status: accepted, November 2026

## Context

The best volume data for manga is in Japanese. Translating synopses, extracting chapter ranges from Japanese descriptions, and resolving ambiguous titles all benefit from an LLM. Tomarr is self-hosted, so it can't pay for users' LLM calls. Gemini's API has a free tier that covers a personal library.

## Decision

- Users paste their own Gemini API key. Without one, LLM features are off and everything else works.
- `llm/base.py` defines the interface. `llm/gemini.py` is the only implementation in MVP, using the official `google-genai` SDK with Pydantic response schemas.
- Deterministic code (regex, fuzzy matching) runs first. The LLM is a fallback for what it can't handle.
- Calls are batched, cached by input hash, and run only inside Commands with backoff on rate-limit errors. The model name is a setting, not a constant.
- The settings page tells users that on Gemini's free tier, Google may use submitted content to improve its products.

## Consequences

- Most users stay inside the free quota, because the LLM only sees what deterministic code couldn't handle.
- Quota numbers aren't hardcoded, since Google changes them.
- Adding Ollama or another provider later means one new adapter, no changes to callers.
