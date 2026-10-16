# Mira · Mehman hotel receptionist

Verified refactor: **106 PostgreSQL regression tests** and production frontend build passed after adding the itinerary planner. The earlier hotel refactor passed **15/15 live feature scenarios**, **10/10 live interpretation cases**, and **11 browser checks**. Itinerary checks are recorded separately in `reports/live-itinerary.json` and `reports/browser-itinerary.json`. See [REFACTOR_REPORT.md](REFACTOR_REPORT.md) for measured results and limits.

A runnable Goa hotel receptionist with Next.js, FastAPI, LangGraph, OpenAI tool planning and grounded response generation, and PostgreSQL. All three properties, nine room types, inventory, tax, and negotiation policies are **fictional**. Holds are temporary inventory claims, not confirmed reservations. No payments.

## Fictional itinerary planner

Mira can create and revise saved day-by-day Goa itineraries using 30 fictional activities in `backend/app/data/goa_itinerary.json`. The model interprets requests and calls the typed `plan_itinerary` tool; the server selects activities from the catalog. Plans support one to seven days, North or South Goa, relaxed/balanced/busy pace, family suitability, interests, and exclusions. The frontend displays day cards and a refresh button, and restores the plan when the session reloads.

Try these messages in order:

- “Plan a three-day relaxed South Goa itinerary with beaches and culture. Make it family-friendly and exclude adventure.”
- “Make that plan busy, keeping the same interests and area.”
- “Change it to nature activities only.”

A plan can use existing stay dates or remain undated. With no duration or stay dates, Mira asks how many days to plan. Changes to travel dates or guest composition mark the saved plan as needing refresh. Planning does not create or cancel hotel holds. Limited matching activities leave free time explicitly instead of inventing extra venues.

All activity venues are invented demo data. Opening hours, routes, travel times, prices, accessibility, and availability are unverified; the planner does not book activities or transport. Run `backend/.venv/bin/python scripts/live_itinerary.py` against a running API for a paid live-model check; results are saved to `reports/live-itinerary.json`.

## Start with Docker Compose

Requires Docker Compose v2, a working Docker daemon, and an OpenAI API key for natural-language AI mode.

```bash
cp .env.example .env
# Edit .env: OPENAI_API_KEY and a separate long random ADMIN_TOKEN.
docker compose up --build
```

Open <http://localhost:3000>. API documentation: <http://localhost:8000/docs>. Readiness: <http://localhost:8000/health>.

The one-shot `migrate` service applies Alembic migrations, seeds deterministic data, and initializes LangGraph's PostgreSQL checkpoint tables before API workers start. PostgreSQL data uses a named volume. `docker compose down` preserves data; `docker compose down -v` deletes it.

`LLM_MODE=openai` is the only supported runtime mode. Mira uses configurable `gpt-4.1-mini` with `OPENAI_SERVICE_TIER=fast` for structured tool planning and natural responses. Missing credentials produce an explicit configuration error; there is no keyword parser or offline agent. Tests mock structured model outputs and exercise the real database services.

## Local development

Requires Python 3.12+, Node 22+, uv, and a running PostgreSQL instance. Configure the root `.env` with `DATABASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL=gpt-4.1-mini`, `OPENAI_SERVICE_TIER=fast`, and a separate `ADMIN_TOKEN`. Keep the existing `.env` when it is already configured.

From the repository root:

```bash
uv sync --project backend --frozen
backend/.venv/bin/python scripts/run_local.py --setup
```

`--setup` applies migrations (including cancellation), idempotently seeds fictional records, initializes checkpoint tables, and starts two API workers. On subsequent starts, omit `--setup`. The launcher reads the root `.env` and overrides stale shell values. The PostgreSQL service must already be running; the launcher does not install or start a database.

In a second terminal:

```bash
cd frontend
npm ci --include=optional
npm run dev
```

Open http://localhost:3000. For production frontend verification use `npm run build`. The latency-oriented default is `gpt-4.1-mini` with fast processing. Historical live feature evaluations used `gpt-4.1` after the smaller model showed more tool-contract failures; those reports do not establish live accuracy or latency for the new default.

The browser calls `http://localhost:8000` by default. For a different host, set `NEXT_PUBLIC_API_URL` **before building** the frontend and set backend `CORS_ORIGIN` to the browser origin. Compose binds only local ports. Publishing to the internet is outside this local case study; use TLS and real identity management before deployment.

## Try a booking

Use future dates; the reproducible example as of October 16, 2026 is:

1. “Goa 2026-11-10 to 2026-11-12 for 2 adults, private pool.”
2. “What about the second option?”
3. “Is the pool heated?” → unknown; no invented amenity.
4. “Give me your best price.” → an engine-validated offer.
5. “Confirm hold.” → revalidates the quote and inventory in one database transaction.

“Cancel my temporary hold” releases its inventory claim and records the cancellation; a cancellation-policy question only retrieves policy. A Cancel temporary hold button is also available. Confirmed external reservations and refunds require staff integration.

Change occupancy or dates before confirmation to see quotes and offers invalidated. “Add breakfast please” after room selection fetches the property's paid add-on, recalculates tax and the stay total, and requires renewed confirmation. Add-on IDs restrict subsequent results to the property's compatible rooms; remove the add-on before comparing other properties.

The right panel shows authoritative requirements, next action, negotiation state, redacted traces, and guest-safe review status. No hidden reasoning is collected or displayed. Reloading restores the session using its browser-held bearer token. “New stay” creates a separate session; the previous state remains in PostgreSQL.

### Manager review

“Demo manager” opens a separate staff interface. Enter `ADMIN_TOKEN` from your local configuration; the token is kept in React memory only, cleared when the panel closes, and never embedded at build time. Example: select Casa Maré's ₹10,752 full-stay quote, then ask “Make it ₹9900 total stay.” The guest sees pending review. A manager may approve/reject using the separate admin token. Approval is persisted and audited; refresh the session or send “Confirm hold” to use the approved amount. No fabricated human reply or response-time promise.

Fictional policy defaults: up to 5% auto approval, above 5% through 10% manager review, above 10% a validated counteroffer. Stored per property in `pricing_policies`; guest APIs do not expose thresholds. Discounts are on the tax-inclusive stay total; a nightly proposal is also tax-inclusive. An unqualified explicit amount asks for nightly versus stay basis. Manager actions resolve related flags; rejecting a discount leaves the original quote available at its original total.

## Verification and evaluations

**Tests delete and recreate application tables in `TEST_DATABASE_URL`. Never point this at development or production data.** The default SQLite run is only a fast smoke check; PostgreSQL is required for concurrency assertions.

```bash
# Root; real PostgreSQL tests and machine-readable reports:
TEST_DATABASE_URL=postgresql+psycopg://mira:password@localhost:5432/mira_test \
  backend/.venv/bin/python scripts/evaluate.py
# SQLite smoke (PostgreSQL tests explicitly skip):
backend/.venv/bin/python scripts/evaluate.py
# Explicitly opt into paid live-model extraction tests:
OPENAI_API_KEY=... backend/.venv/bin/python scripts/live_eval.py
# Frontend:
cd frontend && npm run build
```

See [REFACTOR_REPORT.md](REFACTOR_REPORT.md) for the current architecture and verification. See [EVALUATION_REPORT.md](EVALUATION_REPORT.md), `reports/evaluation.json`, JUnit XML, and [backend/tests/SCENARIOS.md](backend/tests/SCENARIOS.md). For full live feature checks (creates temporary holds on the demo database), run `backend/.venv/bin/python scripts/live_scenarios.py`. The live suites write their own reports only when run. It is not represented as tested without a key.

Run load checks **only on a disposable seeded environment with a configured live model (these consume model requests)**:

```bash
backend/.venv/bin/python scripts/load_smoke.py --workers 6 --iterations 3
backend/.venv/bin/locust -f scripts/locustfile.py --host http://localhost:8000 \
  --headless -u 8 -r 2 -t 30s --csv reports/locust
```

Both exercise actual HTTP search, chat/availability, selection, and hold contention. HTTP 200 can be a correct business refusal; tests independently assert inventory safety. Results describe this environment and workload, not production capacity. Historical offline load reports do not measure this refactor’s model latency.

## API and security contract

- `POST /api/sessions` returns a session UUID and a high-entropy token once.
- Guest session/history/chat/trace/offer/flag endpoints require `Authorization: Bearer <session token>`; only its hash is stored. Property information is public.
- `POST /api/chat` accepts `session_id`, `message`, `idempotency_key`, and optional `expected_version`. Retrying the same message/key returns the stored original response. Reusing a key with different content returns 409. Duplicate holds for an active quote are independently idempotent.
- All `/api/admin/*` routes require `X-Admin-Token`; guest authorization cannot approve offers. Natural idempotency: repeated identical approval/rejection returns the same decision; a conflicting decision returns 409.
- Conversation/history, traces, offers, flags and admin queues use `limit`/`offset`; bounded defaults and a maximum of 100. Session state does not contain unbounded chat history.
- Per-session chat rate limits live in PostgreSQL, so they work across workers. No global/IP limiter is included; session-creation and public reads need an ingress limiter for an internet deployment.
- Generated correlation IDs, JSON request logging, statement/lock timeouts, bounded tools, bounded model calls, pooled connections, and graceful Uvicorn shutdown are included. Tool traces omit free-text requests, child ages, and idempotency keys; technical security flag reasons are admin-only. Conversation text is intentionally persisted and should be treated as personal data, with a retention policy in production.
- Database failure yields a structured 503 and transaction rollback; clients retain the idempotency key. Model failure persists an operational flag and preserves booking state. Timed-out read tools retry once; mutations are never automatically retried. Business errors produce a grounded assistant response and a failed tool trace.

## Source map

- `backend/app/models.py`, `seed.py`, `tools.py`: normalized records, reproducible seed, business logic.
- `schemas.py`, `extraction.py`, `orchestrator.py`: typed patches, bounded LLM planning, tool execution, and generated grounded responses.
- `main.py`: authenticated API and manager review; `alembic/`: migration.
- `frontend/`: responsive App Router/Tailwind dashboard with shadcn-style Radix/CVA button components.
- `scripts/`: mocked structured-model/live evaluation and load probes.

Architecture and tradeoffs: [ENGINEERING_NOTE.md](ENGINEERING_NOTE.md). Five-minute walkthrough: [DEMO_SCRIPT.md](DEMO_SCRIPT.md).

Implementation references: [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses), [LangGraph PostgreSQL checkpoints](https://reference.langchain.com/python/langgraph.checkpoint.postgres). The original Mehman case-study document was not supplied; implementation follows every requirement in the attached master prompt, with verification limits stated in the evaluation report.

### Browser QA

Optional Chrome/Playwright check (expects a configured live-model API and the frontend running):

```bash
npm install --prefix /tmp/mira-browser playwright
PLAYWRIGHT_MODULE=/tmp/mira-browser/node_modules/playwright/index.mjs \
  DEMO_ADMIN_TOKEN=<your-local-admin-token> node scripts/browser-smoke.mjs
```

Set `CHROME_PATH` if Chrome is not at `/usr/bin/google-chrome`. This writes screenshots and a JSON result. The script computes future dates relative to the current day. The test token fallback is only for the isolated local implementation run and is not an application credential. `scripts/verify_runtime.py` can inspect existing PostgreSQL checkpoints and inventory invariants using `DATABASE_URL`.

Probes consume real temporary inventory. Repeating the same workload can exhaust villas for its shared dates until holds expire. Set `MIRA_LOAD_OFFSET_DAYS=50` (or another future offset) for a fresh Locust contention window, or reset your disposable database. `reports/locust-final.json` captures final counters; periodic CSV snapshots can precede the last requests.

### This workspace's verified local setup

The current checkout already has a Python virtual environment and configured root `.env`. Its demo PostgreSQL instance listens on `127.0.0.1:55432`. The host's default Node is too old; a Node 22 runtime was installed locally for verification.

```bash
# Terminal one, repository root (stop an existing API first if port 8000 is occupied):
backend/.venv/bin/python scripts/run_local.py --setup

# Terminal two, repository root:
export PATH=/tmp/mira-node/node_modules/node/bin:$PATH
cd frontend
npm run dev
```

Open http://localhost:3000; API docs are at http://localhost:8000/docs. Subsequent backend starts can omit `--setup`. To exercise cancellation, search, select, explicitly confirm a temporary hold, then say “Cancel my temporary hold” or use its cancellation button. Staff review uses `ADMIN_TOKEN` from your `.env`.

The verification database and Node runtime are under `/tmp`; they are local development conveniences and may be removed by system cleanup. For a durable installation, install Node 22+ and PostgreSQL normally, create the database, and update `.env`, or use Compose. If the existing temporary database is stopped but its files remain, restart it with:

```bash
LD_LIBRARY_PATH=/tmp/mira-pg/root/usr/lib/x86_64-linux-gnu \
  /tmp/mira-pg/root/usr/lib/postgresql/16/bin/pg_ctl \
  -D /tmp/mira-pg/data -l /tmp/mira-pg/server.log \
  -o '-h 127.0.0.1 -p 55432' start
```

For fresh dependency installation, install `uv`, then run `uv sync --project backend --frozen`. Avoid copying `.env.example` over your configured `.env`.

Frontend development writes to `frontend/.next-dev`; production builds use `frontend/.next`. This keeps a production build from deleting assets used by an active development server. Restart a production server after rebuilding it. If the browser shows an unstyled page after switching servers, reload once with Ctrl+Shift+R.
