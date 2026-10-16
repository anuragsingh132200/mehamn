# Mira refactor and verification

The existing application was refactored in place. FastAPI, LangGraph, PostgreSQL, APIs, the frontend, pricing services, and all original test assertions were preserved.

## Conversational changes

Removed the runtime regex/keyword intent parser, phrase-based routing, mutually exclusive intent handling, and normal-response template selection. There is no deterministic/offline conversation mode. A versioned formal system prompt covers professional conduct, multilingual and unrelated conversation, multiple intents, reference resolution, tools, negotiation, escalation, confirmation, cancellation, and truthful responses.

The model submits a native OpenAI function call containing a strict ordered action batch. The backend validates each allowlisted action and supplies identities. It can perform one adaptive planning pass after tool results. A separate structured response uses backend-rendered factual spans with model-written connecting prose. Fixed wording is reserved for validation, security, and outage receipts.

## Preserved application authority

Integer money and Decimal tax rounding; database-backed discount authorization and manager review; occupancy, amenities, budget and date constraints; nightly inventory checks; quote ownership/expiry/fingerprints; row-locked holds; idempotency; session authentication, isolation and concurrency; explicit confirmation; and deterministic date arithmetic remain application-owned.

Cancellation releases only the authenticated session's temporary hold. It locks the hold/inventory records, records `cancelled_at`, invalidates its quote/offers, and preserves travel requirements. Repeated cancellation is safe. Policy questions cannot cancel a hold. External confirmed reservations and refunds require an integration that this demo does not have.

## New schemas

`Interpretation`, `StatePatch` (SET/CLEAR/UNSET), `DateOperation`, `RecommendationReference`, `NegotiationProposal`, `AddOnChange`, `EscalationClassification`, `AgentDecision`, typed tool-call argument variants, `GroundedResponse`/`ResponsePart`, and specific validated quote/search/availability/policy/offer/hold/review result models. Tool and model outputs forbid extra fields. Cancellation has a separate tool and explicit authorization field.

## Graph

receive_message → extract_intent → merge_state → validate_state → route_intent → execute_tools → validate_tool_results → evaluate_escalation → generate_response → persist_trace. Routing may skip tools, or return from escalation evaluation to planning once. Validation and authorization govern execution. Defaults: two planning rounds, four model calls, twelve dispatched calls, bounded recent history and tool context. Internal service calls have an independent cap. Model calls and reported tokens are logged; free-text reasoning is not collected.

A failed planning pass rolls back its mutations. A response failure after a successful hold returns a verified receipt without repeating the mutation. Invalid credentials fail without repeated authentication calls.

## Files changed or introduced

- Agent: `backend/app/agent_schemas.py`, `prompts.py`, `model_gateway.py`, `context.py`, `state_updates.py`, `dispatch.py`, `tool_results.py`, `response.py`, `extraction.py`, `orchestrator.py`.
- Integration: `backend/app/config.py`, `schemas.py`, `tools.py`, `main.py`, `models.py`, `backend/alembic/versions/0002_hold_cancellation.py`.
- UI/config: `frontend/app/page.tsx`, `.env.example`.
- Tests: `backend/tests/conftest.py`, `model_fixtures.py`, `fixtures/legacy_interpretations.json`, `test_agent_contracts.py`, `test_state_updates.py`, `test_llm_agent.py`, `test_cancellation.py`. Original test assertions were retained.
- Tooling/docs: `scripts/evaluate.py`, `live_eval.py`, `live_scenarios.py`, `load_smoke.py`, `locustfile.py`, `browser-smoke.mjs`, README, ENGINEERING_NOTE, REFACTOR_AUDIT, and this report.

## Verification

Original baseline: **50 passed** on PostgreSQL. Intermediate routing run: **53 passed**. Dedicated agent/schema/state run: **33 passed**. After abuse/authentication additions: **89 passed**. Full suite including cancellation: **94 passed, 0 failed, 0 skipped**, real PostgreSQL, **54.46 seconds**. Tests use mocked structured model outputs and real business/database services; these results do not measure live language accuracy. JUnit and scenario diagnostics: `reports/pytest.xml`, `reports/evaluation.json`.

The production frontend builds successfully, including TypeScript checks, after restoring optional native npm dependencies with `npm ci --include=optional`.

Live measurements are recorded separately in `reports/live-evaluation.json` and `reports/live-scenarios.json`. Earlier failures are preserved in `reports/live-scenarios-first-run.json`, `reports/live-scenarios-mini-run.json`, and `reports/live-evaluation-initial.json`; they are not omitted from the assessment. Final live results are appended below after execution.

## Practical limits

The properties, rates and policies are fictional. The app creates temporary holds, not paid confirmed reservations. No PMS, payment, email/SMS, emergency-service, or external cancellation integration exists. Free add-ons require staff review. A flag records a review request; it does not mean staff have responded. Semantic classification and free-form prose remain model-dependent; schema validity and numeric checks cannot prove every hotel claim correct. Prompt injection detection is not exhaustive. Large-scale throughput and long-running reliability require dedicated load/soak testing, provider quota planning, production identity, ingress rate limiting, monitoring, and retention policy. The small concurrent live probe cannot establish production capacity.

Historical pre-refactor load/browser reports are in `reports/pre-refactor/`; root screenshots and older Locust CSVs also describe that baseline unless regenerated explicitly.
