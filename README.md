# Store

A local e-commerce application with product management, search, CSV import, a shopping bag, and simulated checkout. Built as a modular monolith with Python 3.12, FastAPI, PostgreSQL, Jinja2, HTMX, and Bootstrap 5.

All commands below run from the repository root, which contains this README, `compose.yaml`, and `pyproject.toml`.

## Run with Docker

Prerequisites: Docker with Compose v2 and BuildKit support. Run the following from the repository root:

```sh
docker compose up --build -d --wait
```

Compose starts PostgreSQL, runs Alembic migrations, and then starts the application. The `db` and `api` services should become healthy; `migrate` exits successfully with code 0. No products are inserted automatically.

| Destination | URL |
|---|---|
| Store | http://127.0.0.1:5000/ |
| Administration | http://127.0.0.1:5000/admin |
| CSV import | http://127.0.0.1:5000/admin/import |
| Swagger UI | http://127.0.0.1:5000/docs |
| OpenAPI schema | http://127.0.0.1:5000/openapi.json |
| Readiness check | http://127.0.0.1:5000/health/ready |

On the import page, download the empty template or the nine-product sample to populate the store. You can also upload the challenge CSV; invalid rows are reported for review before importing valid rows.

Useful commands, from the repository root:

```sh
docker compose ps
docker compose logs api migrate
docker compose down
```

Stopping Compose preserves the PostgreSQL volume (`store_data` in Compose). Ports are bound to `127.0.0.1`; database credentials in Compose are for local development. The database name, username, and password are all `store` for a fresh local installation. Administration has no authentication and is intended for this local demonstration.

If port 5000 is occupied:

```sh
API_PORT=15000 docker compose up --build -d --wait
```

Then open http://127.0.0.1:15000/. `DB_PORT` can similarly override the default host database port of 5432. Prefer `127.0.0.1` over `localhost` on macOS: IPv6 resolution can reach the AirPlay receiver on port 5000 instead of the application.

### Environment configuration

Docker starts without an `.env` file. For persistent sessions or host development, copy the example from the repository root:

```sh
cp .env.example .env
```

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection for Python running on the host. Compose supplies its own internal connection URL. |
| `SESSION_SECRET` | Stable secret for signed sessions. An empty value generates a temporary secret per application process, invalidating sessions after restart. |

Generate a secret with Python and place the result in `.env`:

```sh
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Do not commit `.env`. Optional Compose overrides `API_PORT`, `DB_PORT`, and `SECURE_COOKIES` default to `5000`, `5432`, and `false`. Set `SECURE_COOKIES=true` when running behind HTTPS. If changing `DB_PORT` for host development, update `DATABASE_URL` to match.

## Run locally with uv

Prerequisites: uv, Python 3.12, and a running Docker daemon. From the repository root:

```sh
uv sync --frozen
cp .env.example .env
docker compose up -d db --wait
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 5000
```

Copy the environment example only if you have not already configured `.env`. If the application container is running, stop it with `docker compose stop api` before starting Uvicorn on the same port.

## Run tests and quality checks

From the repository root, after `uv sync --frozen`:

```sh
uv run playwright install chromium
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest -q
```

On Linux, Playwright may require system libraries; use `uv run playwright install --with-deps chromium` to install them. Docker must be running for Testcontainers. Tests create an isolated PostgreSQL instance, apply real migrations, and reset tables between tests; they do not use the development database. The first run downloads PostgreSQL and Ryuk images. Do not run tests in parallel against the same test database without adding worker isolation.

Optional browser screenshots:

```sh
STORE_CAPTURE_UI=1 uv run pytest -q tests/test_browser.py::test_responsive_layout_and_capture
```

Screenshots are generated under `.impeccable/review/`, excluded from Git and Docker. The maintained interface guidance is in `DESIGN.md`, `DIRECTION.md`, and `PRODUCT.md`.

## Selected architecture decisions

Each entry describes the decision, the implemented approach, and the alternatives considered.

### Modular monolith

**Decision:** Use one application organized into `catalog`, `imports`, `orders`, and `web`, with shared infrastructure in `core`.

**Approach:** Keep HTTP routes thin and business operations in services. HTML and JSON routes reuse those services. The service coordinating a use case owns its transaction, allowing stock, orders, and idempotency to commit together.

**Alternatives considered:** Microservices would introduce distributed coordination for a small application. Organization only by technical layers would make business boundaries less explicit.

### Python and FastAPI backend

**Decision:** Use Python 3.12, FastAPI, Pydantic, Uvicorn, synchronous SQLAlchemy sessions, Alembic, and uv with a committed lockfile.

**Approach:** Pydantic defines request contracts; FastAPI exposes validation and OpenAPI documentation. SQLAlchemy and Alembic handle persistence and schema evolution. Database access uses synchronous routes and services, avoiding blocking calls directly in asynchronous routes. uv installs the locked dependencies for development and Docker builds.

**Alternatives considered:** Flask would require assembling more of the validation and API documentation integration. Asynchronous database access was unnecessary for the scope and would add transaction-management complexity.

### Server-rendered frontend

**Decision:** Render HTML with Jinja2 and progressively enhance interactions with HTMX. Bootstrap 5 supplies common styling, with custom CSS for the application identity.

**Approach:** Serve templates, partial responses, JavaScript, styles, and fonts from the backend. HTMX enhances search and bag updates; ordinary forms retain a fallback without JavaScript. HTML and API requests share business rules. No frontend compilation step is required.

**Alternatives considered:** A React application would add a separate build and client-side state management. Full-page reloads for every interaction would be simpler but less fluid for search and bag updates.

### PostgreSQL with integrated search

**Decision:** Use local PostgreSQL with full-text search and `pg_trgm`, rather than a separate search service.

**Approach:** Alembic creates extensions, triggers, and GIN indexes. A trigger maintains lowercase, accent-normalized search fields covering name, SKU, description, and category. Search combines exact SKU matches, all-term full-text matching with the `simple` dictionary, and name trigram similarity at the default 0.3 threshold. Results rank by exact SKU, text relevance, similarity, and finally ID. Pagination defaults to 20 items and allows up to 100.

**Alternatives considered:** SQLite would differ from the intended concurrency and search environment. Substring matching alone would provide weaker search. An external search engine would add deployment and synchronization costs. This implementation does not provide semantic search or general prefix autocomplete.

### Atomic purchases and concurrency control

**Decision:** Commit stock deductions, the order, its lines, and successful idempotency state in one database transaction.

**Approach:** Consolidate repeated products and process them in ID order. Deduct stock with a conditional `UPDATE` requiring sufficient availability. Read prices on the server and preserve purchased SKU, name, and price in order lines. Any failure rolls back the complete purchase. Retry the whole transaction up to three times only for identified deadlock or serialization failures. Payment is simulated locally.

**Alternatives considered:** Reading stock before an unprotected deduction can oversell. In-memory locks do not coordinate multiple processes. Separate transactions per product can leave partial purchases.

### Optimistic product editing

**Decision:** Require the expected product version for administrative updates and deletion; reject stale writes with HTTP 409.

**Approach:** Include the version in forms and API requests. Update only when the stored version matches, incrementing it on edits, deletion, and purchases that change stock. A stale form must reload the current product before resubmission.

**Alternatives considered:** Last-write-wins could overwrite another edit or a stock change. Holding database locks while a person edits would retain locks for an unpredictable duration.

### Persistent purchase idempotency

**Decision:** Persist purchase idempotency keys and successful results in PostgreSQL.

**Approach:** Scope `Idempotency-Key` by the client UUID supplied in `X-Client-ID` and the purchase operation. Consolidate quantities and sort products before hashing the request. A database uniqueness constraint coordinates simultaneous requests. Equivalent retries return the existing result with HTTP 201; different content under the same key returns 409. Failed transactions roll back their key. Successful records currently have no expiry. The client UUID identifies the idempotency scope; it is not authentication.

**Alternatives considered:** Disabling the purchase button cannot cover network retries or concurrent requests. In-memory keys disappear on restart and do not coordinate instances. Creating a fresh key on every retry could duplicate orders.

### No initial application cache

**Decision:** Start without Redis or an in-process catalog cache.

**Approach:** Use indexed queries, pagination, and bounded results. PostgreSQL remains authoritative for price and stock. Introduce caching only after measurements establish a need and define eligible data, expiry, and invalidation after commit.

**Alternatives considered:** Shared Redis caching adds infrastructure and invalidation work. Per-process caching can diverge between instances. Neither should decide whether a stock deduction is allowed.

### Defer transactional outbox

**Decision:** Do not add an outbox, message broker, or worker for the current implementation.

**Approach:** Keep simulated payment and purchase persistence within the local transaction. Reconsider an outbox when durable external effects, such as notifications or event publication, are introduced. Such a design would persist the event with the business change and require retries and idempotent consumers.

**Alternatives considered:** Adding an outbox now would create unused infrastructure. Publishing external events after commit without a durable record could lose them on failure. An outbox would complement, rather than replace, stock transactions and HTTP idempotency.

### Automated testing and quality checks

**Decision:** Use pytest, HTTPX, Playwright, Ruff, and mypy to validate behavior and maintainability.

**Approach:** Test CRUD, validation, errors, search, CSV import, rollback, stale edits, and purchase idempotency. Concurrency tests use independent connections and coordinated overlap, including competing purchases for the last unit and simultaneous requests sharing an idempotency key. Browser tests exercise actual HTTP flows. The commands above provide reproducible local checks. GitHub Actions and GitHub delivery remain planned; no workflow or publication is currently configured.

**Alternatives considered:** Manual-only checks would miss regressions and timing-sensitive failures. An arbitrary coverage percentage would not establish that important failure and concurrency scenarios behave correctly.

### Testcontainers integration tests

**Decision:** Test persistence and concurrency against an ephemeral PostgreSQL 17.6 instance using Testcontainers.

**Approach:** Start PostgreSQL for the test session, run Alembic migrations, and reset tables between tests. Concurrency tests temporarily hold row locks and observe database lock waits before releasing them to verify real overlap. Playwright uses a live application server connected to this isolated database.

**Alternatives considered:** Database mocks cannot verify SQL constraints or locking behavior. SQLite differs in database capabilities and concurrency. A pre-existing shared database would reduce isolation and require manual setup.

### Signed sessions, CSRF, and checkout continuity

**Decision:** Use signed web sessions and CSRF protection while preserving the bag and purchase key across retries.

**Approach:** Cookies use HttpOnly, SameSite=Lax, and a 24-hour lifetime; HTTPS deployments can enable Secure cookies. Every writing form checks a session CSRF token. The session stores the client identifier, bag quantities, purchase key, and a small receipt summary. Modifying the bag invalidates the purchase key; retrying the same checkout preserves it. The server rechecks prices and availability before purchase. Set a stable `SESSION_SECRET` to retain sessions across restarts or processes. Signing protects integrity, not confidentiality. Administration remains unauthenticated in this local demo; CSRF is not authorization.

**Alternatives considered:** A JavaScript-only bag would weaken the no-JavaScript flow. Trusting client-side prices would allow manipulation. A new purchase key for every retry would undermine idempotency.

### CSV review and explicit partial-import consent

**Decision:** Validate the CSV before writing products and let the user import valid rows or cancel when row-level errors exist.

**Approach:** Accept UTF-8 with an optional BOM, up to 2 MiB and 1,000 rows, with exact columns `name,sku,description,category,price,stock,weight_kg` in any order. Report the logical row number (header is row 1), SKU, field, received value, and reason where applicable. The first valid occurrence of a SKU is eligible; later duplicates and existing SKUs are errors and never overwrite products. Structural errors prevent import; files with no valid rows cannot be confirmed. Fully valid files import directly.

Store mixed-file reviews in PostgreSQL with a session owner and 30-minute expiry. Confirmation checks CSRF and ownership, locks the batch, revalidates its rows and current SKU availability, and commits selected products and completion state together. Repeated confirmation returns the completed result. Cancellation invalidates the batch. New conflicts return 409 and roll back the entire selection. Review history currently has no automatic cleanup. The JSON API remains strict by default; multipart `allow_partial=true` explicitly opts into skipping invalid rows and returns `imported` and `skipped` counts.

The supplied challenge CSV is included at `tests/fixtures/challenge-products.csv` and provides regression coverage. The challenge CSV was downloaded on the **night of October 25, 2026**.

**Alternatives considered:** Silent partial import would make the choice for the user. Mandatory full-file rejection would discard usable rows. Storing rows in a cookie or accepting selected row contents back from the browser would weaken the server's control over the reviewed data.

### XSS and SQL injection protection

**Decision:** Combine shared plain-text input validation, escaped HTML output, a restrictive Content Security Policy, and parameterized SQL queries.

**Approach:** API requests, forms, and CSV rows share validation for product names, descriptions, and categories, rejecting HTML markup, invalid control characters, and unencodable Unicode. Jinja autoescaping covers product data and validation errors; existing records remain readable as escaped text. JavaScript uses text content for notifications. HTMX disables expression evaluation and fragment script execution. CSP blocks inline scripts and event handlers in the store; Swagger uses a nonce and documentation-only CDN/style allowances. Responses also set nosniff, frame, and referrer protections.

SQLAlchemy binds values for writes and searches. A string such as `Robert'); DROP TABLE products;--` remains literal data; legitimate apostrophes remain supported. PostgreSQL tests verify that tables remain intact, and Chromium tests check escaped content and blocked script execution. The approach follows [OWASP XSS guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html) and [SQL injection prevention guidance](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html).

**Alternatives considered:** SQL keyword blacklists would reject legitimate text without securing query construction. Silently stripping content would alter user input. Input validation alone would not protect every HTML rendering context or legacy record.

### Multi-stage Alpine image and minimal configuration

**Decision:** Use Python 3.12 on Alpine 3.22 with separate build and runtime stages, one shared application image, and a minimal environment example.

**Approach:** The builder uses uv 0.12.5, the lockfile, and a BuildKit cache to install execution dependencies. The final image copies the virtual environment and required application files, excludes uv and its cache, and runs as a non-root user. Dependency layers remain separate from application code to preserve build caching. Compose builds the image through `migrate`, reuses it for `api`, and waits for database health and successful migrations. PostgreSQL and its existing volume are preserved. The environment example contains only the host database URL and session secret; optional overrides retain their Compose defaults.

**Alternatives considered:** Debian slim offers broader glibc wheel compatibility. Alpine uses musl, so binary dependency compatibility must be rechecked when changing versions or architectures; the locked dependencies built successfully on the local architecture without compilers. Combining instructions solely to reduce their count would not guarantee smaller images or better caching. See [uv's Docker integration guidance](https://docs.astral.sh/uv/guides/integration/docker/).
