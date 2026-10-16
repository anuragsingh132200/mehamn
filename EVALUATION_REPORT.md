# Evaluation report

Executed October 16, 2026, on the implementation host. No live LLM results are claimed.

## Deterministic suite

**50 passed, 0 failed, 0 skipped**, against real PostgreSQL 16.15, Python 3.12.3, SQLAlchemy 2, FastAPI, and LangGraph. The final JUnit run took 27.50 seconds. Fixtures freeze the clock to October 16, 2026, and use the explicit limited offline parser. Tables are reset between tests in a separate disposable database.

The following are grouped **fixture pass ratios**, not estimates of live-model accuracy. Groups overlap; their counts do not sum to the suite total. The machine-readable report includes individual scenario names and diagnostics.

| Dimension | Passed / executed fixtures |
|---|---|
| intent extraction | 5/5 |
| state updates | 5/5 |
| pricing | 3/3 |
| negotiation compliance | 5/5 |
| escalation | 6/6 |
| grounding | 4/4 |
| booking concurrency | 3/3 |
| next action | 3/3 |
| recommendations | 3/3 |
| protocol and tools | 5/5 |

Additional assertions cover request validation, rate limits, authentication, child ages, expired holds, exact paise threshold boundaries, paid add-on repricing, and log redaction. See [scenario specifications](backend/tests/SCENARIOS.md), [JSON results](reports/evaluation.json), and [JUnit results](reports/pytest.xml).

## Concurrency and integration evidence

- Two independent database sessions compete for a single villa for the same nights: exactly one hold succeeds and the other receives unavailable. This test runs against PostgreSQL, with actual `FOR UPDATE` locking; it does not substitute SQLite.
- Two simultaneous messages for the same conversation produce versions 1 and 2 and retain all four user/assistant messages.
- Duplicate confirmation with the same idempotency key returns the identical stored response and creates one hold. A changed body under the same key receives 409.
- The running two-worker API created actual PostgreSQL LangGraph checkpoints and committed holds. A post-load invariant query found zero overbooked room-nights. See [runtime evidence](reports/runtime.json).
- Alembic upgrade, deterministic seed, and checkpoint initialization succeeded against PostgreSQL. Exactly three properties and nine room types were verified.

## Frontend and browser

Next.js 15.5.28 production build passed under Node 22; TypeScript checks passed. Desktop and 390px mobile browser checks used the production server and a real Chrome browser. All nine checks passed, with no page errors: initial render, database-backed recommendations, unknown policy, pending review, a real manager approval, a discounted temporary hold, persistence after reload, actual tool traces, and no mobile horizontal overflow.

[Browser JSON](reports/browser-smoke.json), [welcome screenshot](reports/welcome-desktop.png), [booking screenshot](reports/booking-desktop.png), [mobile screenshot](reports/booking-mobile.png).

## Measured local HTTP probe

Six concurrent clients, three iterations each, deterministic extraction, two Uvicorn workers, PostgreSQL checkpointing enabled. **70 requests in 5.845 seconds**, **11.98 requests/second**, **0% HTTP failure rate**. Each client searches hotels, creates a session, searches shared stay dates, selects when available, and attempts a hold. Inventory depletion intentionally reduces the number of selection and hold calls.

| Operation | Requests | Median ms | p95 ms | HTTP failure rate |
|---|---:|---:|---:|---:|
| chat_hold_contention | 8 | 689.72 | 759.45 | 0% |
| chat_search_and_availability | 18 | 955.39 | 1721.20 | 0% |
| chat_select | 8 | 852.59 | 950.29 | 0% |
| hotel_search | 18 | 50.28 | 129.30 | 0% |
| session_create | 18 | 53.69 | 162.55 | 0% |

[Raw measured report](reports/load-smoke.json). HTTP success includes correct business refusals when the last unit is gone; it is not a claim that every attempted booking succeeds.

## Measured Locust run

A separate short run targeted eight users (ramp 2/second) for 12 seconds with fresh shared dates (`MIRA_LOAD_OFFSET_DAYS=50`). Final counters: **170 requests**, **0 failures**, **14.68 observed requests/second**, approximate aggregate median **33 ms**, p95 **480 ms**. It included property searches, sessions, chat searches/availability, room selection, and hold contention. [Final machine report](reports/locust-final.json); periodic CSV snapshots may precede final requests.

An earlier follow-up run was interrupted by an API restart and is excluded from performance conclusions; its nonzero failures are retained separately in [the interrupted-run report](reports/locust-interrupted.json). Repeated probes can exhaust real demo inventory until holds expire, so fresh dates were used for the final contention run.

These small local probes are reproducibility checks, not a saturation benchmark, sustained capacity claim, or measurement of OpenAI inference latency. Results depend on the host, seed, existing holds, checkpoint overhead, and workload mix. Longer steady-state tests and actual-model latency measurements remain necessary before sizing production.

## Verification limits

- **Live OpenAI extraction was not run:** no API key was available. The application uses the actual Responses structured-output SDK path when configured; missing credentials produce a clear 503 instead of a simulated AI answer. The optional paid live suite is provided and writes its own report only when executed.
- **Docker images and Compose startup were not executed:** the host user could not access the Docker daemon even outside the sandbox. `docker compose config --quiet` passed using the example environment. The same migrations, seed, checkpoints, two-worker API, and standalone frontend ran directly against real PostgreSQL. Container execution remains unverified.
- Browser verification covers the main happy path, approval, grounding, persistence, and responsive layout. It does not constitute an accessibility audit or every possible interaction.
- The original Mehman case-study document was not included; coverage is mapped to the supplied master prompt.
