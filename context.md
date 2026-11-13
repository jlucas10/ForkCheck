# ForkCheck: Project Context (allergen lookup MVP)

> Tagline: **Know what you can eat.**
> Before launch: check App Store name, domain and trademark availability.

## What this is

ForkCheck is a mobile app that answers one question for people with multiple food allergies: **"Does this fit my profile?"**

Two lookups, one safety filter:

1. **Scan** a packaged food (barcode) and see if it fits. **Ships in the launch release (v1.0).**
2. **Ask about a restaurant** ("what can I eat at Chipotle?", "does the pad thai have peanut?") and get an answer grounded in the restaurant's own allergen documents, with citations. **Ships in v1.1 (January), not in the launch release.**

US-only for the MVP: the allergen list is the US top 9 plus custom allergens, and disclaimers are written for the US.

The founder has multiple food allergies and EoE and is the first user.

**Not in the MVP:** meal planning, meal/symptom tracking beyond a simple scan history, EoE and GLP-1 modes, HealthKit. See the post-MVP backlog.

## Goals, in priority order

1. **Submit v1.0 (profile + safety filter + barcode scan) to the App Store by Dec 12-15, 2026** so it can be live before Christmas. Apple's holiday slowdown tends to hit around Dec 23-27, so there is no slack after the submission date. Ship a useful app that the founder uses every week on groceries.
2. **Be a serious backend and security portfolio piece:** Auth0 and IAM done properly, structured extraction with validation, a deterministic safety layer, and (in v1.1) production RAG over messy documents with an evaluation harness and real numbers.
3. **Learn security fundamentals by building** (Security+ topics mapped to real code). See `docs/security.md`.

If a task serves none of these, push back on it. If something threatens the Dec 12-15 submission, cut scope, never safety tests.

### Never cut, in any schedule

- The safety filter and its unit and property-based tests
- Account deletion (App Store requirement for apps with sign-in)
- Privacy policy and disclaimers
- Auth0 and IAM implementation, and the learning log

## Core principles

1. **The LLM proposes, code decides.** An LLM may extract allergens and phrase answers. A deterministic safety filter in plain code decides what fits a user's profile.
2. **Retrieval narrows, the filter decides.** Vector and keyword search find candidate items. They never decide that something is allergen-free.
3. **Every answer is grounded.** Each result shows the source, and page where applicable, and last-verified date. If there is no source, the answer is "no data", never a guess.

## How to work with me (read this first)

I'm building this to learn and as a portfolio piece, so I need to understand every line. Work in small steps and **stop after every addition**.

An "addition" is any new file, feature, endpoint, migration, component, test suite or meaningful change. After each one:

1. **Stop.** Do not start the next addition until I say to continue.
2. **What you added:** files created or changed, one or two lines each.
3. **Code walkthrough:** section by section, in plain language.
4. **Thought process:** how you approached it and in what order.
5. **Why it's coded this way:** alternatives considered and the tradeoffs (safety, simplicity, performance, cost, flexibility). Point out connections to the core principles or safety rules.
6. **How to test it:** exact commands or steps.
7. **New concepts:** briefly explain any library, pattern or concept the first time it appears (for example JWKS, RBAC, hybrid search, row-level security).
8. **Security note:** one or two lines on which security concept the addition touches; add it to `docs/security.md`.
9. **Then ask** whether I have questions or changes before moving on.

Working preferences:

- **Do not run shell commands or code in the terminal for me.** Create and edit files with the file tools only; I run commands myself.
- If a task is large, propose a plan of small steps first and wait for approval before writing code.

## Non-goals

- No diagnosis or treatment claims. Never write copy that says the app "treats", "cures" or "diagnoses".
- **Never claim a food or dish is guaranteed safe.** Formulas and recipes change, and kitchens have cross-contact.
- No emergency guidance beyond "follow your allergy action plan and call emergency services."
- No social feed, no calorie tracking, no workout features.
- Never replace a doctor, allergist or dietitian.

## Stack

| Layer              | Choice                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------- |
| Mobile             | Expo (React Native) + TypeScript (strict). **Needs an Expo development build, not Expo Go** (`react-native-auth0` uses native code) |
| Backend            | Python, FastAPI, Pydantic v2; `uv`, ruff, mypy, pytest                                                  |
| Database           | Postgres on Supabase, pgvector and full-text search enabled from the start                              |
| Auth               | Auth0: Apple + Google sign-in, RBAC, MFA for privileged roles                                           |
| Packaged food data | Open Food Facts (ODbL: keep attribution), fetched live by barcode and cached. USDA subset is optional.  |
| Restaurant data (v1.1) | Public allergen PDFs and pages; Playwright for JS-rendered pages; pdfplumber or Camelot for tables  |
| LLM                | Claude with structured outputs, validated by Pydantic                                                   |
| Embeddings (v1.1)  | One embedding model, stored in pgvector                                                                 |
| Ingestion          | Python jobs on GitHub Actions cron                                                                      |
| File storage       | Cloudflare R2 (source documents, label photos)                                                          |
| Hosting            | Railway or Render first; AWS Fargate in hardening                                                       |

Check each source's terms and robots.txt before scraping or calling an API. Store attribution and the original document for every record.

## Architecture

**Packaged foods (v1.0): live lookup with caching.**
barcode -> check own database -> if missing, fetch from Open Food Facts by barcode -> alias-dictionary match + LLM structured extraction -> compare and score confidence -> disagreement or low confidence goes to the review queue (stays unsafe) -> cache in Postgres with source link, `verified_at`, `prompt_version`, `model`. If Open Food Facts has no record or no ingredient list, the result is "no data" (unsafe).

**Scan request (online):** barcode -> item lookup (above) -> deterministic filter against the user's profile -> result with source, date and warnings. Unknown product = unsafe.

**Offline jobs:** hash and diff each source (unchanged = skip, no LLM call); re-verify cached items that pass their freshness window.

**Restaurant pipeline (v1.1):**
fetch -> hash and diff -> store original in R2 -> parse (tables, ingredient lists) -> chunk by menu item or table row, keeping source, page and row -> alias match + LLM extraction -> compare and score confidence -> review queue -> publish with source link, `verified_at`, `prompt_version`, `model` -> embed.

**Restaurant question (v1.1):** resolve restaurant -> **hybrid retrieval** (vector + keyword) of candidate menu items and source chunks -> **deterministic filter** against the profile -> the LLM writes a short answer **only from the filtered items and retrieved chunks**, citing document and page -> response always includes the confirm-with-staff and cross-contact reminder.

## Allergy handling (most important section)

### Detection (two independent paths; either flags an item)

1. **Alias dictionary (deterministic):** ingredient words to allergens (whey, casein, ghee -> milk; albumin -> egg; semolina, spelt -> wheat; tahini -> sesame; and so on). Hidden sources matter.
2. **LLM extraction:** reads ingredient lists, allergen tables and "contains" / "may contain" statements into structured tags.

If the two disagree **or confidence is below threshold**, the item goes to the review queue and stays **unsafe until reviewed**.

### Blank cells and missing information (strict)

- Absence of a mark is **not** evidence of "free". A blank cell in an allergen table, or an allergen missing from an ingredient list, is `unknown` by default.
- A source document can carry a flag `blank_means_free`, set **only by a human reviewer** after reading that document's legend or statement (for example "this chart lists every allergen in each item"). Code applies the flag; the LLM never decides it.
- `free` status requires either an explicit source statement or a reviewer-set flag, and is stored with the evidence.

### Severity drives the filter

| Severity    | `contains` | `may_contain` / shared kitchen       | Unknown  | Stale data                 |
| ----------- | ---------- | ------------------------------------ | -------- | -------------------------- |
| Intolerance | Excluded   | Allowed with warning                 | Excluded | Warning                    |
| Allergy     | Excluded   | Excluded by default (user can allow) | Excluded | Warning                    |
| Severe      | Excluded   | Always excluded                      | Excluded | Excluded until re-verified |

Set a freshness window per source type in configuration (restaurant data goes stale faster than packaged data) and apply the "Stale data" column.

### Copy rules

- Say **"No listed allergens found"** or **"Fits your profile"**. Never "safe" or "allergen-free."
- Always show source, page where applicable, and last-verified date.
- Packaged foods: remind users to check the current label.
- Restaurant results (v1.1) always prompt the user to confirm with staff and mention cross-contact.
- Provide a **"Report an error"** button on every result.

### Embeddings rule

Embeddings may retrieve candidates or propose alias candidates into the review queue. They never mark anything as free of an allergen.

## Auth and access

- Auth0 tenant (shared with Reelsmith). Native app: Authorization Code + PKCE via `react-native-auth0`. API registered with RBAC and "Add Permissions in the Access Token."
- Roles: `user` (assigned by an Auth0 Action on first login), `reviewer` (user + `review:allergens`), `admin` (reviewer + `manage:catalog`, `manage:users`, `read:audit_log`).
- **MFA required** for `reviewer` and `admin` (Auth0 Action). Check which features your Auth0 plan includes.
- FastAPI validates every token (signature via JWKS, `iss`, `aud`, expiry) and uses `require_permission(...)`. Check permissions, never role names.
- Key users by the Auth0 `sub` claim, never email. Store it as text (it is not a UUID).
- Log sensitive actions (review decisions, catalog changes, role changes, deletion) to `audit_log`.
- Short-lived access tokens; refresh tokens with rotation on mobile; tokens in secure device storage only.
- **Known MVP tradeoff:** the app talks only to FastAPI, and FastAPI connects to Postgres with a privileged connection, so row-level security is **bypassed** and FastAPI is the only enforcement layer. Postgres RLS with Auth0 Third-Party Auth is added in hardening as a second layer. That later work needs: an Auth0 Action adding a `role: "authenticated"` claim to every token, and RLS policies using `auth.jwt() ->> 'sub'` (not `auth.uid()`). Verify against current Supabase docs when we get there.

## Security learning log

Keep `docs/security.md` growing with the build, mapping each addition to a Security+ style topic: OAuth2/OIDC and PKCE, JWT validation, RBAC and least privilege, MFA, secrets handling, audit logging, input validation and rate limiting, CORS, dependency and secret scanning (Dependabot, `pip-audit`, CodeQL), encryption in transit and at rest, data deletion, and a short STRIDE threat model. RLS and second-layer enforcement come in hardening.

## Core schema

- `users`: id, auth0_sub (text, unique)
- `allergens`: id, name, is_top9
- `allergen_aliases`: allergen_id, alias, notes
- `user_allergies`: user_id, allergen_id, severity (intolerance / allergy / severe), allow_may_contain, notes
- `items`: id, kind (product / menu_item), name, barcode (nullable), restaurant_id (nullable), source_document_id (nullable), source_url, ingredients_text, category, verified_at, embedding (vector, v1.1)
- `item_allergens`: item_id, allergen_id, status (contains / may_contain / free / unknown), detected_by (alias / llm / both / manual), confidence, verified, evidence, prompt_version, model
- `review_queue`: id, item_id, reason (disagreement / low_confidence / user_report), status, resolved_by, resolved_at
- `data_reports`: id, user_id, item_id, message, created_at
- `lookups`: id, user_id, kind (scan / restaurant_question), item_id (nullable), query, result, filter_version, created_at (covers scan history and every answer's `filter_version`)
- `llm_calls`: id, purpose, model, prompt_version, tokens_in, tokens_out, latency_ms, cost_usd
- `audit_log`: id, actor_sub, action, target_type, target_id, details (json), created_at
- `eval_labels`: id, kind (extraction / retrieval), input_text, expected (json)
- v1.1 restaurant tables: `restaurants` (id, name, allergen_url, last_fetched_at), `source_documents` (id, restaurant_id nullable, url, file_hash, storage_key, fetched_at, blank_means_free), `document_chunks` (id, source_document_id, page, row_ref, text, embedding)

## Safety rules (never break these)

1. The safety filter is plain deterministic code with unit and property-based tests (Hypothesis). Never move allergen decisions into a prompt.
2. **Unknown allergen status = unsafe.** Apply the severity table exactly.
3. An item is flagged if **either** the alias dictionary or the LLM finds an allergen.
4. A blank or missing entry is `unknown`, not `free`, unless a reviewer-set `blank_means_free` flag applies.
5. (v1.1) The LLM answers only from filtered, retrieved items and chunks. It may only reference item ids that exist, and every claim must cite a source chunk. Reject and retry otherwise.
6. If there is no source for a question, the answer is "no data found", never a guess.
7. Every lookup stores the `filter_version` that produced it.
8. Never write "safe", "allergen-free" or "guaranteed" in user-facing copy.
9. Any change to the filter, alias table or severity rules ships with new tests in the same PR.

## Data and privacy

- Allergy data is sensitive: minimal collection, encrypted at rest.
- **Account deletion** (Postgres and Auth0) ships in v1.0 (App Store requirement). Data export follows in v1.1.
- No ad networks or data-reselling analytics SDKs. No personal data in URLs or logs.

## Evaluation (the portfolio evidence)

Run on every prompt, model or filter change:

1. **Safety (v1.0, required):** generated profiles and items (property-based). **Allergen misses must be zero.**
2. **Extraction (small at v1.0, grows in v1.1):** at least 20 hand-labeled ingredient lists for launch, growing to 50+ including 10+ real, messy restaurant documents. Report precision and recall per allergen.
3. **Retrieval (v1.1):** 30+ labeled questions with expected items. Report recall@k and the share of answers with correct citations.

Track cost and latency per call in `llm_calls`.

## Code conventions

- Typed Python; Pydantic models for every request, response and LLM output. Routers by domain (`items`, `allergies`, `lookup`, `reviews`).
- Mobile: TypeScript strict mode.
- Migrations through Supabase/Alembic only; never edit the schema by hand.
- Every PR: tests pass, filter tests untouched or extended, no secrets committed. Secrets in environment variables for now.

## v1.0 plan: submit by Dec 12-15, 2026

Roughly 4 build weeks from Nov 13. There is no buffer, so cut scope before moving the date.

### Sprint 0: Foundation and Auth0 (about Nov 13-20)

- [x] `/api` skeleton: health check, settings, one test; CI workflow written
- [ ] Verify locally: install `uv`, run tests, lint, format check and mypy
- [ ] First commit and GitHub repo so CI runs
- [ ] **Start Apple Developer Program enrollment now** (it can take days)
- [ ] Auth0: shared tenant, native app, API with RBAC and "Add Permissions in the Access Token", `user` / `reviewer` / `admin` roles and permissions, first-login Action; Apple and Google sign-in last
- [ ] FastAPI: JWT validation (JWKS, `iss`, `aud`, expiry) and `require_permission()`
- [ ] Supabase project with pgvector and full-text search; first migration (Alembic)
- [ ] Expo development build with Auth0 sign-in on the phone
- [ ] Start `docs/security.md`; `/app`, `/ingest` and `/docs` folders created when they get content
- **Done when:** you sign in on your phone, call an authenticated endpoint, and a test proves a token without the right permission gets a 403.

### Sprint 1: Safety core and packaged-food detection (about Nov 21-Dec 4)

- [ ] Alias dictionary (top 9 plus common custom allergens) with tests
- [ ] Multi-allergy profile with severity, may-contain preference and custom allergens (API and screen)
- [ ] Safety filter implementing the severity table and blank-cell rule, with unit and property-based tests
- [ ] Open Food Facts live lookup by barcode with caching; no-data handling
- [ ] LLM extraction into Pydantic schemas; store `prompt_version` and `model`; log calls in `llm_calls`
- [ ] Disagreement and low-confidence routing to `review_queue`; reviews protected by `review:allergens`; `audit_log`
- [ ] Small extraction eval (20+ labeled items) with precision and recall per allergen
- **Done when:** the filter tests show no item containing a user's allergen, at any severity, ever passes, and you can state an extraction accuracy number.

### Sprint 2: Scan flow, deletion and launch prep (about Dec 5-11)

- [ ] Barcode scan screen -> lookup -> filter -> result with source, date and warnings; unknown product = unsafe with a clear message
- [ ] "Report an error" button feeding `review_queue`; scan history (`lookups`)
- [ ] Account deletion (Postgres and Auth0)
- [ ] Privacy policy, terms and disclaimers; App Privacy labels
- [ ] Name, domain and trademark check; demo account for App Review (sign-in goes through Auth0)
- [ ] TestFlight build for yourself; use it on real groceries
- **Done when:** a TestFlight build works end to end on real products.

### Submission (Dec 12-15)

- [ ] Screenshots, metadata, support URL, age rating
- [ ] Review-guideline check on health and allergy claims; consider a legal review of the disclaimers
- **Done when:** the app is submitted.

## v1.1 plan (January)

### Restaurant ingestion and RAG lookup

- [ ] Verify each restaurant's allergen documents are public and parseable (Texas Roadhouse, Wendy's, Chipotle, Panda Express, Krispy Kreme); start with 2-3
- [ ] Fetch, parse, chunk (keeping page and row), extract, review, publish and embed
- [ ] Hybrid retrieval (vector + keyword) scoped to a restaurant
- [ ] Question flow: retrieve -> filter -> grounded LLM answer with citations and the confirm-with-staff reminder
- [ ] Retrieval eval (30+ questions); extraction eval extended with real restaurant documents
- **Done when:** you can ask about a covered restaurant, get a cited answer that respects your profile, and report recall@k and extraction accuracy on messy documents.

### Polish and beta

- [ ] Chef card: shareable screen listing the user's allergies and severity for restaurant staff
- [ ] Data export
- [ ] MFA enforced for `reviewer` and `admin` (if not already done)
- [ ] TestFlight with 10-20 testers from allergy communities; track retention, scans, lookups, error reports

## Post-MVP backlog (do not start before v1.0 is submitted)

- More restaurants; user-uploaded menu photos with human review; translatable chef card
- Meal planner (retrieve -> filter -> LLM proposes from survivors -> filter re-checks)
- EoE mode (trigger exclusions, elimination phases, texture scoring) and GLP-1 mode
- Meal and symptom logging, insights (patterns only), HealthKit / Health Connect read sync, doctor-ready PDF report
- Hardening: AWS ECS Fargate + RDS, Secrets Manager, GitHub OIDC, CloudWatch, Postgres RLS with Auth0 Third-Party Auth, Auth0 config as code, separate dev and prod tenants

## Metrics

- Allergen misses by the filter: **must be zero**
- Extraction precision and recall per allergen; (v1.1) retrieval recall@k and citation correctness
- Alias/LLM disagreement rate and review turnaround; user error reports per 100 lookups
- Share of scans that return "no data"
- LLM cost and p95 latency per purpose
- Beta users, day-30 retention, scans and lookups per active user
