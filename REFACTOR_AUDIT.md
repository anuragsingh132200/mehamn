# Conversation refactor audit

Baseline before changes: **50 passed in 29.57s**, real PostgreSQL; `reports/refactor-baseline.xml`.

| Existing area | Finding | Action |
|---|---|---|
| `app/extraction.py` | Runtime regex/keyword parser, keyword injection detection, mutually exclusive intent, no recent messages | Remove runtime parser. Use structured model planning, multi-intent classification, bounded context and semantic risk classification. |
| `app/orchestrator.py` | Intent-specific routing, static response templates, selection/negotiation/add-on conflict, thirteen unconditional sequential nodes | Replace conversational routing with validated model-proposed tools and conditional graph edges. Keep mechanical guards and state mutation in Python. |
| `app/schemas.py` | Generic patch field names, limited negotiation shape, untyped nested tool outputs | Add strict semantic schemas, typed tool calls, references, date operations, ambiguity and negotiation models; validate tool outputs. |
| State and references | State durable, but history omitted; changing requirements discards selection without preserving referents | Preserve bounded history and pending questions. Resolve indices against pre-turn recommendations, invalidate dependent artifacts, and allow explicit reprice of referenced room. |
| Business services | Correct integer pricing, exact discount thresholds, nightly availability, transactions and idempotency | Preserve these services; expose them through an allowlisted adapter with server-owned session/quote arguments. |
| API | Session row lock, bearer authorization, admin-only approval, persisted messages/checkpoints | Preserve API contracts and concurrency. Roll back partial turn writes before persisting model-failure review events. |
| Tests/evaluation | Existing tests use runtime parser and expect some fixed words | Keep assertions; replace model boundary with test-only structured fixtures. Add independent plan/response/SDK contract tests. Historical load and browser reports remain historical, not claims about live LLM behavior. |

The production application will have one OpenAI-backed conversation path. Test doubles live only in `backend/tests`; no runtime parser or offline mode fallback. This improves flexibility but does not guarantee perfect handling of every possible utterance; unresolved references require clarification, and provider outages remain explicit.
