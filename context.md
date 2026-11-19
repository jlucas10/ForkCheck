# ForkCheck: Project Context (production RAG first, a little AWS)

> Tagline: **Know what you can eat.**
> Before launch: check App Store name, domain and trademark availability.

## What this is

ForkCheck is a mobile app that answers one question for people with multiple food allergies: **"Does this fit my profile?"**

Two lookups, one safety filter:

1. **Scan** a packaged food (barcode) and see if it fits.
2. **Ask about a restaurant** ("what can I eat at Chipotle?", "does the pad thai have peanut?") and get an answer grounded in the restaurant's own allergen documents, with citations.

The founder has multiple food allergies and EoE and is the first user.

**Not in the MVP:** meal planning, meal/symptom tracking beyond a simple log, EoE and GLP-1 modes, HealthKit. See the post-MVP backlog.

## Goals, in priority order

1. **Ship a useful MVP to the App Store** that the founder uses every week (groceries and eating out).
2. **Be a serious backend portfolio piece, centered on production RAG:** retrieval over messy documents, structured extraction with validation, an evaluation harness with real numbers, and a deterministic safety layer.
3. **Learn Terraform and a handful of AWS services** by using them where they fit (storage, queueing, scheduled workers, monitoring). AWS is a supporting skill here, not the whole project. The main API stays on a simple host.

The mobile app is deliberately thin. If a task serves none of these goals, push back on it.

## Core principles

1. **The LLM proposes, code decides.** An LLM may extract allergens and phrase answers. A deterministic safety filter in plain code decides what fits a user's profile.
2. **Retrieval narrows, the filter decides.** Vector and keyword search find candidate items. They never decide that something is allergen-free.
3. **Every answer is grounded.** Each result shows the source document, page and last-verified date. If there is no source, the answer is "no data", never a guess.
4. **AWS resources are created by Terraform.** No clicking in the console for anything that lives in `infra/`.

## How to work with me (read this first)

I'm building this to learn and as a portfolio piece, so I need to understand every line. Work in small steps and **stop after every addition**.

An "addition" is any new file, feature, endpoint, migration, component, test suite, Terraform module or meaningful change. After each one:

1. **Stop.** Do not start the next addition until I say to continue.
2. **What you added:** files created or changed, one or two lines each.
3. **Code walkthrough:** section by section, in plain language.
4. **Thought process:** how you approached it and in what order.
5. **Why it's coded this way:** alternatives considered and the tradeoffs (safety, simplicity, performance, cost, flexibility). Point out connections to the core principles or safety rules.
6. **How to test it:** exact commands or steps (for Terraform: what `plan` should show and how to verify after `apply`).
7. **New concepts:** briefly explain any library, pattern, AWS service or concept the first time it appears (for example hybrid search, chunking, Terraform state, IAM roles, OIDC federation, dead-letter queues).
8. **Then ask** whether I have questions or changes before moving on.

If a task is large, propose a plan of small steps first and wait for approval before writing code.

## Non-goals

- No diagnosis or treatment claims. Never write copy that says the app "treats", "cures" or "diagnoses".
- **Never claim a food or dish is guaranteed safe.** Formulas and recipes change, and kitchens have cross-contact.
- No emergency guidance beyond "follow your allergy action plan and call emergency services."
- No social feed, no calorie tracking, no workout features.
- Never replace a doctor, allergist or dietitian.

## Stack

| Layer                   | Choice                                                                                                                                                                                                                                                                                                     |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Mobile                  | Expo (React Native) + TypeScript (strict), thin client                                                                                                                                                                                                                                                     |
| Backend API             | Python, FastAPI, Pydantic v2, containerized, hosted on Railway or Render                                                                                                                                                                                                                                   |
| Database                | Postgres on Supabase, **pgvector and full-text search enabled from the start**                                                                                                                                                                                                                             |
| Auth                    | Auth0: Apple + Google sign-in, RBAC, MFA for privileged roles                                                                                                                                                                                                                                              |
| LLM                     | Claude with structured outputs, validated by Pydantic                                                                                                                                                                                                                                                      |
| Embeddings              | One embedding model, stored in pgvector                                                                                                                                                                                                                                                                    |
| Packaged food data      | Open Food Facts (ODbL: keep attribution) + USDA FoodData Central subset                                                                                                                                                                                                                                    |
| Restaurant data         | Public allergen PDFs and pages; pdfplumber or Camelot for tables; Playwright for JS-rendered pages (later)                                                                                                                                                                                                 |
| **AWS (via Terraform)** | **S3** (source documents, label photos), **SQS + dead-letter queue** and **Lambda** (container image) for per-document processing, **EventBridge Scheduler** for scheduled fetches, **CloudWatch** alarms, **ECR**, **IAM** (GitHub OIDC), **Secrets Manager** for worker secrets, an **AWS Budget** alarm |
| IaC                     | Terraform in `/infra`, S3 remote state with locking                                                                                                                                                                                                                                                        |
| CI/CD                   | GitHub Actions; OIDC to AWS (no long-lived keys in CI)                                                                                                                                                                                                                                                     |

Check each source's terms and robots.txt before scraping. Store attribution and the original document for every record.

**Honest tradeoff:** the API runs outside AWS, so it reaches S3 and SQS with a tightly scoped IAM user whose keys live in the host's environment variables (rotate them; document this). Moving the API to ECS Fargate later removes that and is in the backlog.

## Architecture

**Offline (scheduled ingestion):**

- _Early (sprint 1):_ GitHub Actions cron fetches Open Food Facts data and stores originals in S3.
- _Restaurant pipeline, first version (sprint 3):_ a plain Python script (local or GitHub Actions) runs the whole flow below in one process, so the RAG can be built and evaluated before any AWS plumbing.
- _Restaurant pipeline, AWS version (sprint 4):_ EventBridge Scheduler -> fetcher Lambda (hash and diff; unchanged source = skip, no LLM call; store original in S3; enqueue one SQS message per changed document) -> processor Lambda (parse tables and ingredient lists -> chunk by menu item or table row, keeping source, page and row -> alias-dictionary match + LLM structured extraction -> compare and score confidence -> disagreement or low confidence goes to the review queue and stays unsafe -> publish to Postgres with source link, `verified_at`, `prompt_version`, `model` -> embed). Failed messages land in the dead-letter queue and raise a CloudWatch alarm.
- JS-rendered pages (Playwright) don't fit Lambda well. Start with static PDFs and pages; handle JS pages later with a container task.

**Online (user request):**
app -> FastAPI -> Postgres (Supabase) and the LLM.

- _Scan:_ barcode -> item lookup -> deterministic filter against the user's profile -> result with source and warnings. Unknown product = unsafe.
- _Restaurant question:_ resolve restaurant -> **hybrid retrieval** (vector + keyword) of candidate menu items and source chunks -> **deterministic filter** against the profile -> the LLM writes a short answer **only from the filtered items and retrieved chunks**, citing document and page -> response always includes the confirm-with-staff and cross-contact reminder.

## Allergy handling (most important section)

### Detection (two independent paths; either flags an item)

1. **Alias dictionary (deterministic):** ingredient words to allergens (whey, casein, ghee -> milk; albumin -> egg; semolina, spelt -> wheat; tahini -> sesame; and so on). Hidden sources matter.
2. **LLM extraction:** reads ingredient lists, allergen tables and "contains" / "may contain" statements into structured tags.

If the two disagree **or confidence is below threshold**, the item goes to the review queue and stays **unsafe until reviewed**.

### Severity drives the filter

| Severity    | `contains` | `may_contain` / shared kitchen       | Unknown  | Stale data                 |
| ----------- | ---------- | ------------------------------------ | -------- | -------------------------- |
| Intolerance | Excluded   | Allowed with warning                 | Excluded | Warning                    |
| Allergy     | Excluded   | Excluded by default (user can allow) | Excluded | Warning                    |
| Severe      | Excluded   | Always excluded                      | Excluded | Excluded until re-verified |

Restaurant data goes stale faster than packaged data. Set a freshness window per source type and apply the "Stale data" column.

### Copy rules

- Say **"No listed allergens found"** or **"Fits your profile"**. Never "safe" or "allergen-free."
- Always show source, page and last-verified date.
- Restaurant results always prompt the user to confirm with staff and mention cross-contact.
- Packaged foods: remind users to check the current label.
- Provide a **"Report an error"** button on every result.

### Embeddings rule

Embeddings may retrieve candidates or propose alias candidates into the review queue. They never mark anything as free of an allergen.

## Auth and access

- Auth0 tenant. Native app: Authorization Code + PKCE via `react-native-auth0`. API registered with RBAC and "Add Permissions in the Access Token."
- Roles: `user` (assigned by an Auth0 Action on first login), `reviewer` (user + `review:allergens`), `admin` (reviewer + `manage:catalog`, `manage:users`, `read:audit_log`).
- **MFA required** for `reviewer` and `admin` (Auth0 Action). Check which features your Auth0 plan includes.
- FastAPI validates every token (signature via JWKS, `iss`, `aud`, expiry) and uses `require_permission(...)`. Check permissions, never role names.
- Key users by the Auth0 `sub` claim, never email.
- Log sensitive actions (review decisions, catalog changes, role changes, deletion) to `audit_log`.
- MVP: the app talks only to FastAPI, which enforces permissions. Postgres RLS with Auth0 Third-Party Auth is added in hardening as a second layer.

## Terraform and CI/CD rules

1. Layout: `infra/modules/` (s3, queue, lambda-worker, scheduler, iam-oidc, alarms) and `infra/envs/dev`. Remote state in S3 with locking. Start with one environment.
2. **Least-privilege IAM:** separate roles for the fetcher, processor, API user and the GitHub OIDC role. No wildcard actions on `*` without a written reason.
3. Encrypt S3 and block public access. Tag every resource (`project`, `env`). Set an AWS Budget alarm from the start.
4. Secrets are never committed and never printed in logs.
5. **GitHub Actions:**
   - _CI (every PR):_ lint, type-check, unit and property tests, `terraform fmt -check`, `terraform validate`, and a security scan (Checkov or tfsec).
   - _Plan (PRs touching `infra/`):_ `terraform plan`, posted to the PR.
   - _Apply (merge to main):_ `terraform apply` behind a protected environment with manual approval; build and push worker images to ECR.
   - _Eval (on prompt, model, filter or alias changes, and nightly):_ run the extraction, retrieval and safety evals and fail on regression.
6. No long-lived AWS keys in CI: GitHub OIDC only.

## Core schema

- `users`: id, auth0_sub (unique)
- `allergens`: id, name, is_top9
- `allergen_aliases`: allergen_id, alias, notes
- `user_allergies`: user_id, allergen_id, severity (intolerance / allergy / severe), allow_may_contain, notes
- `restaurants`: id, name, allergen_url, last_fetched_at
- `source_documents`: id, restaurant_id (nullable), url, file_hash, storage_key (S3), fetched_at
- `document_chunks`: id, source_document_id, page, row_ref, text, embedding (vector)
- `items`: id, kind (product / menu_item), name, barcode (nullable), restaurant_id (nullable), source_document_id, ingredients_text, category, verified_at, embedding (vector)
- `item_allergens`: item_id, allergen_id, status (contains / may_contain / free / unknown), detected_by (alias / llm / both / manual), confidence, verified, prompt_version, model
- `review_queue`: id, item_id, reason (disagreement / low_confidence / user_report), status, resolved_by, resolved_at
- `data_reports`: id, user_id, item_id, message, created_at
- `scan_history`: user_id, item_id, scanned_at, result
- `eval_labels`: id, kind (extraction / retrieval), input_text, expected (json)
- `llm_calls`: id, purpose, model, prompt_version, tokens_in, tokens_out, latency_ms, cost_usd
- `audit_log`: id, actor_sub, action, target_type, target_id, details (json), created_at

## Safety rules (never break these)

1. The safety filter is plain deterministic code with unit and property-based tests (Hypothesis). Never move allergen decisions into a prompt.
2. **Unknown allergen status = unsafe.** Apply the severity table exactly.
3. An item is flagged if **either** the alias dictionary or the LLM finds an allergen.
4. The LLM answers only from filtered, retrieved items and chunks. It may only reference item ids that exist, and every claim must cite a source chunk. Reject and retry otherwise.
5. If retrieval finds no source for a question, the answer is "no data found", never a guess.
6. Every answer stores the `filter_version` that produced it.
7. Never write "safe", "allergen-free" or "guaranteed" in user-facing copy.
8. Any change to the filter, alias table or severity rules ships with new tests in the same PR.

## Data and privacy

- Allergy data is sensitive: minimal collection, encrypted at rest and in transit.
- Build **data export and account deletion** early (App Store requires account deletion for apps with sign-in).
- No ad networks or data-reselling analytics SDKs. No personal data in URLs or logs.

## Evaluation (the portfolio evidence)

Three harnesses, run in CI on every prompt, model or filter change:

1. **Extraction:** 50+ hand-labeled ingredient lists and restaurant allergen tables (include 10+ real, messy restaurant documents). Report precision and recall per allergen.
2. **Retrieval:** 30+ labeled questions with expected items. Report recall@k and the share of answers with correct citations.
3. **Safety:** generated profiles and items (property-based). **Allergen misses must be zero.**

Track cost and latency per call in `llm_calls`.

## Code conventions

- Typed Python; Pydantic models for every request, response and LLM output. Routers by domain (`items`, `allergies`, `lookup`, `reviews`).
- Mobile: TypeScript strict mode.
- Migrations through Supabase/Alembic only; never edit the schema by hand.
- Every PR: tests pass, filter tests untouched or extended, `terraform plan` reviewed when `infra/` changes, no secrets committed.

## MVP sprints (two weeks each; sprints 3 and 4 may take longer)

### Sprint 0: Foundation

- [ ] Monorepo: `/app` (Expo), `/api` (FastAPI), `/ingest` (Python), `/infra` (Terraform)
- [ ] Supabase project with pgvector and full-text search
- [ ] Auth0: native app, API with RBAC, `user` / `reviewer` / `admin`, first-login Action, Apple and Google sign-in
- [ ] FastAPI skeleton on Railway or Render:
  - [x] Health check and settings (including Auth0 domain and audience)
  - [x] JWT validation (JWKS signature, `iss`, `aud`, expiry)
  - [x] `require_permission()`
  - [x] Containerize (Dockerfile)
    - [x] Auth0 roles, and permissions created
  - [ ] Deploy to Railway or Render
- [x] CI on GitHub Actions: lint, type-check, tests
- **Done when:** you sign in on your phone, call an authenticated endpoint, and a test proves a token without the right permission gets a 403.

### Sprint 1: Packaged catalog, detection, eval v1 and first Terraform

- [ ] **Terraform intro:** S3 state bucket, an S3 bucket for source documents, GitHub OIDC role, AWS Budget alarm; `plan` on PRs and `apply` on merge
- [ ] Ingest Open Food Facts (and a USDA subset) on a GitHub Actions cron; hash-diff to skip unchanged sources; originals in S3
- [ ] Alias dictionary (top 9 plus common custom allergens) with tests
- [ ] LLM extraction into Pydantic schemas; store `prompt_version` and `model`; log every call in `llm_calls`
- [ ] Disagreement and low-confidence routing to `review_queue`; reviews protected by `review:allergens`; `audit_log`
- [ ] Extraction eval harness (50+ labeled items) with precision and recall per allergen, running in CI
- **Done when:** a few thousand products are tagged and traceable to sources, you can state an extraction accuracy number, and the S3 bucket and OIDC role exist only because of Terraform.

### Sprint 2: Profile, safety filter and barcode scan (the daily-use core)

- [ ] Multi-allergy profile with severity, may-contain preference and custom allergens
- [ ] Safety filter implementing the severity table, with unit and property-based tests
- [ ] Barcode scan -> lookup -> filter -> result with source, date and warnings; unknown product = unsafe with a clear message
- [ ] "Report an error" button feeding `review_queue`; scan history
- **Done when:** you use it on real groceries for a week, and tests show no item containing a user's allergen, at any severity, ever passes the filter.

### Sprint 3: Restaurant RAG (plain Python pipeline, no new AWS)

Get the RAG working and measured first. Do not add SQS or Lambda in this sprint.

- [ ] Pick 5-10 restaurants you actually eat at, and confirm each publishes a usable allergen document before committing to it
- [ ] Pipeline as a plain Python script (run locally or on a GitHub Actions cron): fetch, hash-diff, store original in the existing S3 bucket, parse, chunk (keeping page and row), extract, compare, review queue, publish, embed
- [ ] Hybrid retrieval (vector + keyword) scoped to a restaurant
- [ ] Structured first: answer from `item_allergens` when the question is about a specific dish or allergen; use chunk retrieval for free-text notes (cross-contact, preparation, ingredient substitutions)
- [ ] Question flow: retrieve -> filter -> grounded LLM answer with citations and the confirm-with-staff reminder
- [ ] Retrieval eval (30+ questions) and extraction eval extended with real restaurant documents
- **Done when:** you can ask about a covered restaurant, get a cited answer that respects your profile, and report recall@k and extraction accuracy on messy documents.

### Sprint 4: Move the restaurant pipeline to AWS

Only start this once the sprint 3 eval numbers are good.

- [ ] **Terraform:** SQS queue + dead-letter queue, fetcher and processor Lambdas (container images in ECR), EventBridge Scheduler, CloudWatch alarms for DLQ depth and Lambda errors
- [ ] Split the script into a fetcher (hash-diff, S3, enqueue one message per changed document) and a processor (parse through embed); processing must be idempotent, so the same message twice gives the same result
- [ ] Re-run the extraction and retrieval evals against the AWS pipeline in CI; numbers must match sprint 3
- **Done when:** a scheduled run ingests the restaurants end to end on AWS, eval numbers are unchanged, and a poisoned document lands in the DLQ and triggers an alarm.

### Sprint 5: Polish and beta

- [ ] Chef card: shareable screen listing the user's allergies and severity for restaurant staff
- [ ] Data export and account deletion (Postgres, S3 and Auth0)
- [ ] MFA enforced for `reviewer` and `admin`
- [ ] TestFlight with 10-20 testers from allergy communities; track retention, scans, lookups, error reports
- **Done when:** you have real retention numbers and a list of the top complaints.

### Sprint 6: App Store submission

- [ ] Apple Developer Program enrollment; name, domain and trademark check
- [ ] Privacy policy, terms and disclaimers; App Privacy labels
- [ ] Demo account for App Review (sign-in goes through Auth0)
- [ ] Screenshots, metadata, support URL, age rating
- [ ] Review-guideline check on health and allergy claims; consider a legal review of the disclaimers
- **Done when:** the app is submitted.

## Post-MVP backlog (do not start before submission)

- Move the API to ECS Fargate in a VPC; RDS Postgres; Secrets Manager for everything; CloudWatch for the API; remove the long-lived IAM user
- Postgres RLS with Auth0 Third-Party Auth; Auth0 config as code; separate dev and prod environments
- More restaurants; Playwright for JS-rendered pages; user-uploaded menu photos with human review; translatable chef card
- Meal planner (retrieve -> filter -> LLM proposes from survivors -> filter re-checks)
- EoE mode and GLP-1 mode; meal and symptom logging, insights (patterns only), HealthKit / Health Connect read sync, doctor-ready PDF report

## Metrics

- Allergen misses by the filter: **must be zero**
- Extraction precision and recall per allergen; retrieval recall@k; citation correctness
- Alias/LLM disagreement rate and review turnaround; user error reports per 100 lookups
- LLM cost and p95 latency per purpose; monthly AWS cost
- Ingestion success rate and DLQ depth
- Beta users, day-30 retention, scans and lookups per active user
