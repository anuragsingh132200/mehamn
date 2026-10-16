# Vercel deployment

Deploy from the repository root. `vercel.json` defines a Next.js frontend
and a FastAPI backend using Vercel Services. API requests, `/health`, and
API documentation reach FastAPI; other paths reach Next.js.

On Vercel, the frontend defaults to the same domain for API calls. A
`NEXT_PUBLIC_API_URL` override remains available for a separately hosted API.
Local builds keep the existing `http://localhost:8000` default.

## Required configuration

Connect a hosted PostgreSQL database and configure these Vercel environment
variables before deploying:

- `DATABASE_URL`: the provider's PostgreSQL URL with TLS enabled, such as
  `postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require`. The application
  selects the installed psycopg driver automatically.
- `DATABASE_URL_UNPOOLED`: when provided by Neon, this direct connection takes
  precedence over `DATABASE_URL` so PostgreSQL startup timeouts are supported.
- `OPENAI_API_KEY`: the server-side model credential.
- `ADMIN_TOKEN`: a separate, long random staff credential.
- `OPENAI_MODEL`: `gpt-4.1-mini`, or another compatible model.
- `OPENAI_SERVICE_TIER`: `fast` (default) for lower latency; use `default` for
  standard processing. Existing environment values override application defaults.

Use a separate database for preview environments. Local `.env` files and
credentials are excluded from deployment uploads by `.vercelignore`.

## Initialize the hosted database

With the production `DATABASE_URL` set in the environment, run these once
from `backend/`, using the project's Python environment:

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seed
.venv/bin/python -m app.checkpoints
```

These commands create and seed the schema without copying local conversations.
API workers do not run migrations. Never run the test suite against this database.

## Publish and verify

```bash
vercel login
vercel link
vercel --prod
```

After deployment, verify `/health`, creation and restoration of a guest session,
and a chat request from the deployed frontend. A successful frontend build alone
does not verify database or model connectivity.
